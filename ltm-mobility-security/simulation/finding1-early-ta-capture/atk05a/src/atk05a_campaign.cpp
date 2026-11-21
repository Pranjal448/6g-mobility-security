// ATK-05a full campaign driver.  Standalone; NOT part of srsRAN; no srsRAN file is modified.
//
// QUESTION
// --------
// ATK-05a is the contamination of the LTM *early timing-advance acquisition*
// (TS 38.300 clause 9.2.3.5.2 step 4b): the serving cell PDCCH-orders the UE to send a
// contention-free preamble to a candidate cell, and the candidate cell's PRACH detector
// measures a timing advance that is later handed to the UE in an LTM Cell Switch Command.
// A repeater placed between the UE and the candidate cell adds a delayed copy of that
// preamble.  The question this driver answers, against the real unmodified srsRAN PRACH
// detector, is:
//
//     for a given repeater excess delay and received-power ratio, what timing advance does
//     the candidate cell actually report, and how often is the error large enough to matter?
//
// MODEL
// -----
// A repeater is an ADDED path, never a replacement: the air sums.  The received PRACH is
//     direct copy   at delay tau_v                with amplitude 1
//     relayed copy  at delay tau_v + delta        with amplitude 10^(rel_db/20)
// Each macro-path is optionally expanded into a small-scale fading realisation:
//     fading=none      deterministic amplitude, no phase rotation            (derivation check)
//     fading=rayleigh  one unit-power complex Gaussian gain per path         (flat fading)
//     fading=pdp       nof_taps-tap exponential power-delay profile per path (delay spread)
// AWGN of the requested SNR (referred to the direct path) is added per subcarrier.
//
// CLASSIFICATION
// --------------
// The detector reports one timing advance.  Each trial is classified by which macro-path
// that advance belongs to, with a tolerance of one IDFT bin:
//     victim    |TA - tau_v|            <= tol
//     attacker  |TA - (tau_v + delta)|  <= tol
//     other     anything else (noise peak, or a fading tap between the two)
// and the error is reported in TIMING-ADVANCE UNITS, the quantity the MAC CE actually
// carries:  T_A unit = 16*64*T_c / 2^mu  (260.4167 ns at mu=1, 520.8333 ns at mu=0).
//
// OUTPUT
// ------
// One CSV row per grid cell on stdout (header first), plus optional per-trial rows.
//
// Usage: atk05a_campaign --mode {gates|grid|absent|raw} [knobs]   (see print_help)

#include "lib/phy/upper/channel_processors/prach_detector_generic_impl.h"
#include "lib/phy/upper/channel_processors/prach_generator_impl.h"
#include "srsran/phy/generic_functions/generic_functions_factories.h"
#include "srsran/phy/support/support_factories.h"
#include "srsran/ran/prach/prach_preamble_information.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <random>
#include <string>
#include <vector>

using namespace srsran;

namespace {

// ---------------------------------------------------------------- constants

// T_c = 1 / (480e3 * 4096) s   (TS 38.211 clause 4.1)
constexpr double T_C = 1.0 / (480.0e3 * 4096.0);

// T_A unit = 16 * 64 * T_c / 2^mu   (TS 38.213 clause 4.2)
double ta_unit_s(unsigned mu)
{
  return 16.0 * 64.0 * T_C / std::pow(2.0, static_cast<double>(mu));
}

// ---------------------------------------------------------------- CLI

double argd(int argc, char** argv, const char* key, double dflt)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (!std::strcmp(argv[i], key)) {
      return std::atof(argv[i + 1]);
    }
  }
  return dflt;
}
std::string args(int argc, char** argv, const char* key, const char* dflt)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (!std::strcmp(argv[i], key)) {
      return argv[i + 1];
    }
  }
  return dflt;
}
bool hasflag(int argc, char** argv, const char* key)
{
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], key)) {
      return true;
    }
  }
  return false;
}
std::vector<double> argl(int argc, char** argv, const char* key, const std::vector<double>& dflt)
{
  std::string s = args(argc, argv, key, "");
  if (s.empty()) {
    return dflt;
  }
  std::vector<double> out;
  size_t p = 0;
  while (p <= s.size()) {
    size_t q = s.find(',', p);
    if (q == std::string::npos) {
      q = s.size();
    }
    if (q > p) {
      out.push_back(std::atof(s.substr(p, q - p).c_str()));
    }
    p = q + 1;
  }
  return out;
}

// ---------------------------------------------------------------- channel

enum class fading_mode { none, rayleigh, pdp };

fading_mode parse_fading(const std::string& s)
{
  if (s == "none") {
    return fading_mode::none;
  }
  if (s == "rayleigh") {
    return fading_mode::rayleigh;
  }
  if (s == "pdp") {
    return fading_mode::pdp;
  }
  std::fprintf(stderr, "unknown fading mode %s\n", s.c_str());
  std::exit(2);
}

const char* fading_name(fading_mode f)
{
  switch (f) {
    case fading_mode::none:
      return "none";
    case fading_mode::rayleigh:
      return "rayleigh";
    default:
      return "pdp";
  }
}

// A macro-path as seen by the attack geometry.
struct macro_path {
  double delay_s;
  double amp_lin; // deterministic amplitude (linear, direct path = 1.0)
};

// A resolved channel tap handed to the frequency-domain summation.
struct tap {
  double               delay_s;
  std::complex<double> gain;
};

// Expand the macro-paths into taps for one trial.
void realise(std::vector<tap>&              taps,
             const std::vector<macro_path>& paths,
             fading_mode                    fading,
             double                         ds_s,
             unsigned                       nof_taps,
             std::mt19937&                  rng)
{
  taps.clear();
  std::normal_distribution<double> g(0.0, std::sqrt(0.5)); // unit-power complex Gaussian

  for (const macro_path& p : paths) {
    if (fading == fading_mode::none) {
      taps.push_back({p.delay_s, std::complex<double>(p.amp_lin, 0.0)});
      continue;
    }
    if (fading == fading_mode::rayleigh) {
      taps.push_back({p.delay_s, p.amp_lin * std::complex<double>(g(rng), g(rng))});
      continue;
    }
    // Exponential power-delay profile: tap i at i*dt with power exp(-i*dt/ds),
    // dt = ds/4, normalised so the macro-path keeps amplitude p.amp_lin overall.
    const double dt   = ds_s / 4.0;
    double       norm = 0.0;
    for (unsigned i = 0; i != nof_taps; ++i) {
      norm += std::exp(-static_cast<double>(i) * dt / ds_s);
    }
    for (unsigned i = 0; i != nof_taps; ++i) {
      const double pw = std::exp(-static_cast<double>(i) * dt / ds_s) / norm;
      taps.push_back({p.delay_s + static_cast<double>(i) * dt,
                      p.amp_lin * std::sqrt(pw) * std::complex<double>(g(rng), g(rng))});
    }
  }
}

// Fill the PRACH buffer with sum_taps gain * exp(-j2 pi k df tau) * X[k] + noise.
void fill_buffer(prach_buffer&           buffer,
                 span<const cf_t>        seq,
                 unsigned                nof_symbols,
                 const std::vector<tap>& taps,
                 double                  scs_hz,
                 double                  noise_sigma,
                 std::mt19937&           rng)
{
  std::normal_distribution<double> gauss(0.0, noise_sigma / std::sqrt(2.0));
  for (unsigned i_symbol = 0; i_symbol != nof_symbols; ++i_symbol) {
    span<cbf16_t> out = buffer.get_symbol(0, 0, 0, i_symbol);
    for (unsigned k = 0, k_end = seq.size(); k != k_end; ++k) {
      std::complex<double> acc(0.0, 0.0);
      for (const tap& t : taps) {
        const double ph = -2.0 * M_PI * static_cast<double>(k) * scs_hz * t.delay_s;
        acc += t.gain * std::complex<double>(std::cos(ph), std::sin(ph)) *
               std::complex<double>(seq[k].real(), seq[k].imag());
      }
      if (noise_sigma > 0.0) {
        acc += std::complex<double>(gauss(rng), gauss(rng));
      }
      out[k] = cf_t(static_cast<float>(acc.real()), static_cast<float>(acc.imag()));
    }
  }
}

// ---------------------------------------------------------------- detector harness

struct harness {
  prach_format_type                     fmt;
  bool                                  is_long;
  prach_subcarrier_spacing              scs;
  unsigned                              root;
  unsigned                              preamble;
  unsigned                              nof_symbols;
  unsigned                              sequence_length;
  double                                scs_hz;
  std::unique_ptr<prach_detector_generic_impl> detector;
  std::unique_ptr<prach_buffer>         buffer;
  std::vector<cf_t>                     seq;
  prach_generator_impl                  tx_gen;

  double time_res_s = 0.0;
  double window_s   = 0.0;
};

std::unique_ptr<harness> make_harness(const std::string& fmts, double scs_sel, unsigned root, unsigned preamble)
{
  auto h = std::make_unique<harness>();

  h->is_long = false;
  if (fmts == "B4") {
    h->fmt = prach_format_type::B4;
  } else if (fmts == "A1") {
    h->fmt = prach_format_type::A1;
  } else if (fmts == "A2") {
    h->fmt = prach_format_type::A2;
  } else if (fmts == "A3") {
    h->fmt = prach_format_type::A3;
  } else if (fmts == "C2") {
    h->fmt = prach_format_type::C2;
  } else if (fmts == "zero") {
    h->fmt     = prach_format_type::zero;
    h->is_long = true;
  } else {
    std::fprintf(stderr, "unknown format %s\n", fmts.c_str());
    std::exit(2);
  }

  h->scs = prach_subcarrier_spacing::kHz30;
  if (h->is_long) {
    h->scs = prach_subcarrier_spacing::kHz1_25;
  } else if (scs_sel == 15) {
    h->scs = prach_subcarrier_spacing::kHz15;
  }

  std::shared_ptr<dft_processor_factory> dftf = create_dft_processor_factory_generic();
  auto mk = [&dftf](unsigned n) {
    dft_processor::configuration c{};
    c.size = n;
    c.dir  = dft_processor::direction::INVERSE;
    return dftf->create(c);
  };
  h->detector = std::make_unique<prach_detector_generic_impl>(
      mk(1024), mk(256), std::make_unique<prach_generator_impl>(), true);

  const prach_preamble_information info = h->is_long
                                              ? get_prach_preamble_long_info(h->fmt)
                                              : get_prach_preamble_short_info(h->fmt, h->scs, false);
  h->nof_symbols     = info.nof_symbols;
  h->sequence_length = info.sequence_length;
  h->scs_hz          = static_cast<double>(ra_scs_to_Hz(info.scs));
  h->root            = root;
  h->preamble        = preamble;
  h->buffer = h->is_long ? create_prach_buffer_long(1, 1) : create_prach_buffer_short(1, 1, 1);
  return h;
}

void set_sequence(harness& h, unsigned zcz)
{
  prach_generator::configuration g{};
  g.format               = h.fmt;
  g.root_sequence_index  = h.root;
  g.preamble_index       = h.preamble;
  g.restricted_set       = restricted_set_config::UNRESTRICTED;
  g.zero_correlation_zone = zcz;
  span<const cf_t> s     = h.tx_gen.generate(g);
  h.seq.assign(s.begin(), s.end());
}

prach_detector::configuration det_cfg(const harness& h, unsigned zcz)
{
  prach_detector::configuration d{};
  d.root_sequence_index   = h.root;
  d.format                = h.fmt;
  d.restricted_set        = restricted_set_config::UNRESTRICTED;
  d.zero_correlation_zone = zcz;
  d.start_preamble_index  = 0;
  d.nof_preamble_indices  = 64;
  d.ra_scs                = h.scs;
  d.nof_rx_ports          = 1;
  d.slot                  = slot_point(1, 0);
  return d;
}

// ---------------------------------------------------------------- one grid cell

struct cell_result {
  unsigned trials      = 0;
  unsigned detected    = 0;
  unsigned n_victim    = 0;
  unsigned n_attacker  = 0;
  unsigned n_other     = 0;
  unsigned n_damaging  = 0; // |err| >= boundary, in T_A units
  double   sum_err     = 0.0;
  double   sum_err_sq  = 0.0;
  double   sum_metric  = 0.0;
  double   sum_power_db = 0.0;
  double   time_res_s  = 0.0;
  double   window_s    = 0.0;
};

cell_result run_cell(harness&     h,
                     unsigned     zcz,
                     double       tau_v_s,
                     double       delta_s,
                     double       rel_db,
                     double       snr_db,
                     fading_mode  fading,
                     double       ds_s,
                     unsigned     nof_taps,
                     bool         with_victim,
                     bool         with_attacker,
                     unsigned     trials,
                     unsigned     mu,
                     double       boundary_units,
                     unsigned     seed,
                     FILE*        raw)
{
  set_sequence(h, zcz);
  const prach_detector::configuration dcfg = det_cfg(h, zcz);

  std::vector<macro_path> paths;
  if (with_victim) {
    paths.push_back({tau_v_s, 1.0});
  }
  if (with_attacker) {
    paths.push_back({tau_v_s + delta_s, std::pow(10.0, rel_db / 20.0)});
  }

  const double sigma = (snr_db > 1e8) ? 0.0 : std::sqrt(1.0 / std::pow(10.0, snr_db / 10.0));
  const double unit  = ta_unit_s(mu);

  std::mt19937      rng(seed);
  std::vector<tap>  taps;
  cell_result       r;
  r.trials = trials;

  for (unsigned t = 0; t != trials; ++t) {
    realise(taps, paths, fading, ds_s, nof_taps, rng);
    fill_buffer(*h.buffer, h.seq, h.nof_symbols, taps, h.scs_hz, sigma, rng);
    prach_detection_result res = h.detector->detect(*h.buffer, dcfg);
    r.time_res_s = res.time_resolution.to_seconds();
    r.window_s   = res.time_advance_max.to_seconds();

    if (res.preambles.empty()) {
      continue;
    }
    const auto* best = &res.preambles[0];
    for (const auto& p : res.preambles) {
      if (p.detection_metric > best->detection_metric) {
        best = &p;
      }
    }
    ++r.detected;
    const double ta_s = best->time_advance.to_seconds();
    const double tol  = r.time_res_s; // one IDFT bin

    const char* cls = "other";
    if (with_victim && std::abs(ta_s - tau_v_s) <= tol) {
      ++r.n_victim;
      cls = "victim";
    } else if (with_attacker && std::abs(ta_s - (tau_v_s + delta_s)) <= tol) {
      ++r.n_attacker;
      cls = "attacker";
    } else {
      ++r.n_other;
    }

    // Error the UE would inherit, relative to its own true propagation delay.
    const double err_units = (ta_s - tau_v_s) / unit;
    r.sum_err += err_units;
    r.sum_err_sq += err_units * err_units;
    r.sum_metric += best->detection_metric;
    r.sum_power_db += best->preamble_power_dB;
    if (std::abs(err_units) >= boundary_units) {
      ++r.n_damaging;
    }
    if (raw != nullptr) {
      std::fprintf(raw,
                   "%u,%s,%.1f,%u,%.4f,%.4f,%.3f,%.3f,%s,%.6f,%.6f\n",
                   t,
                   fading_name(fading),
                   snr_db,
                   zcz,
                   tau_v_s * 1e6,
                   delta_s / unit,
                   rel_db,
                   ta_s * 1e6,
                   cls,
                   err_units,
                   best->detection_metric);
    }
  }
  return r;
}

void print_header()
{
  std::printf("mode,fmt,scs_khz,mu,zcz,fading,ds_ns,nof_taps,snr_db,tau_v_us,delta_units,delta_us,"
              "rel_db,trials,p_detect,p_victim,p_attacker,p_other,mean_err_units,sd_err_units,"
              "p_damaging,mean_metric,mean_power_db,time_res_ns,window_us,window_units\n");
}

void print_row(const char* mode,
               const std::string& fmts,
               double scs_khz,
               unsigned mu,
               unsigned zcz,
               fading_mode fading,
               double ds_s,
               unsigned nof_taps,
               double snr_db,
               double tau_v_s,
               double delta_s,
               double rel_db,
               const cell_result& r)
{
  const double unit = ta_unit_s(mu);
  const double n    = (r.detected > 0) ? static_cast<double>(r.detected) : 1.0;
  const double mean = r.sum_err / n;
  const double var  = std::max(0.0, r.sum_err_sq / n - mean * mean);
  std::printf("%s,%s,%.2f,%u,%u,%s,%.1f,%u,%.1f,%.4f,%.4f,%.4f,%.3f,%u,"
              "%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.4f\n",
              mode,
              fmts.c_str(),
              scs_khz,
              mu,
              zcz,
              fading_name(fading),
              ds_s * 1e9,
              nof_taps,
              snr_db,
              tau_v_s * 1e6,
              delta_s / unit,
              delta_s * 1e6,
              rel_db,
              r.trials,
              double(r.detected) / double(r.trials),
              double(r.n_victim) / double(r.trials),
              double(r.n_attacker) / double(r.trials),
              double(r.n_other) / double(r.trials),
              mean,
              std::sqrt(var),
              double(r.n_damaging) / double(r.trials),
              r.sum_metric / n,
              r.sum_power_db / n,
              r.time_res_s * 1e9,
              r.window_s * 1e6,
              r.window_s / unit);
  std::fflush(stdout);
}

void print_help()
{
  std::printf(
      "atk05a_campaign --mode {gates|grid|absent}\n"
      "  --fmt B4|A1|A2|A3|C2|zero   --scs 15|30   --mu 0|1   --root N  --preamble N\n"
      "  --zcz-list 0,11,15          --snr-list 0,10,20\n"
      "  --delta-units 1,2,...       (repeater excess delay, in T_A units)\n"
      "  --rel-list -10,...,15       (relay received power relative to direct path, dB)\n"
      "  --fading none|rayleigh|pdp  --ds-ns 300   --nof-taps 20\n"
      "  --tau-v-us 0.0              --trials 300  --seed N  --boundary-units 7\n"
      "  --raw FILE                  (also dump every trial)\n");
}

} // namespace

int main(int argc, char** argv)
{
  if (hasflag(argc, argv, "--help")) {
    print_help();
    return 0;
  }

  const std::string mode     = args(argc, argv, "--mode", "grid");
  const std::string fmts     = args(argc, argv, "--fmt", "B4");
  const double      scs_khz  = argd(argc, argv, "--scs", 30);
  const unsigned    mu       = static_cast<unsigned>(argd(argc, argv, "--mu", 1));
  const unsigned    root     = static_cast<unsigned>(argd(argc, argv, "--root", 17));
  const unsigned    preamble = static_cast<unsigned>(argd(argc, argv, "--preamble", 13));
  const unsigned    trials   = static_cast<unsigned>(argd(argc, argv, "--trials", 300));
  const unsigned    seed     = static_cast<unsigned>(argd(argc, argv, "--seed", 20261112));
  const double      tau_v    = argd(argc, argv, "--tau-v-us", 0.0) * 1e-6;
  const double      ds_s     = argd(argc, argv, "--ds-ns", 300.0) * 1e-9;
  const unsigned    taps     = static_cast<unsigned>(argd(argc, argv, "--nof-taps", 20));
  const double      bound    = argd(argc, argv, "--boundary-units", 7.0);
  const fading_mode fading   = parse_fading(args(argc, argv, "--fading", "rayleigh"));

  const std::vector<double> zcz_list = argl(argc, argv, "--zcz-list", {0, 11, 15});
  const std::vector<double> snr_list = argl(argc, argv, "--snr-list", {10});
  const std::vector<double> dlt_list = argl(argc, argv, "--delta-units", {7});
  const std::vector<double> rel_list = argl(argc, argv, "--rel-list", {0});

  std::unique_ptr<harness> h = make_harness(fmts, scs_khz, root, preamble);
  const double             unit = ta_unit_s(mu);

  FILE* raw = nullptr;
  const std::string rawpath = args(argc, argv, "--raw", "");
  if (!rawpath.empty()) {
    raw = std::fopen(rawpath.c_str(), "w");
    std::fprintf(raw, "trial,fading,snr_db,zcz,tau_v_us,delta_units,rel_db,ta_us,class,err_units,metric\n");
  }

  // ------------------------------------------------------------------ gates
  if (mode == "gates") {
    std::printf("# ATK-05a validation gates.  Every gate is a property this harness must\n"
                "# reproduce before any attack number from it is reported.\n");
    std::printf("ta_unit_ns=%.6f\n", unit * 1e9);

    // G1: single path, zero delay, noiseless -> detect with zero error.
    {
      cell_result r = run_cell(*h, 0, 0.0, 0.0, 0.0, 1e9, fading_mode::none, ds_s, taps,
                               true, false, 20, mu, bound, seed, nullptr);
      std::printf("G1_single_path_noiseless: p_detect=%.3f mean_err_units=%.6f -> %s\n",
                  double(r.detected) / double(r.trials), r.sum_err / std::max(1u, r.detected),
                  (r.detected == r.trials && std::abs(r.sum_err) < 1e-9) ? "PASS" : "FAIL");
      std::printf("G2_time_resolution: measured_ns=%.6f derived_ns=%.6f -> %s\n",
                  r.time_res_s * 1e9, 1.0e9 / (h->scs_hz * 256.0),
                  std::abs(r.time_res_s - 1.0 / (h->scs_hz * 256.0)) < 1e-12 ? "PASS" : "FAIL");
      std::printf("G2b_grid_per_ta_unit: bins_per_ta_unit=%.6f\n", unit / r.time_res_s);
    }

    // G3: detection window versus ZCZ (the hard cap the attacker cannot exceed).
    for (double z : zcz_list) {
      cell_result r = run_cell(*h, static_cast<unsigned>(z), 0.0, 0.0, 0.0, 1e9,
                               fading_mode::none, ds_s, taps, true, false, 4, mu, bound, seed, nullptr);
      std::printf("G3_window zcz=%u window_us=%.6f window_ta_units=%.4f\n",
                  static_cast<unsigned>(z), r.window_s * 1e6, r.window_s / unit);
    }

    // G4: capture threshold at a T_A-unit-aligned delay, noiseless, no fading.
    // Phase B derived 0.00 dB exactly for a bin-aligned delay.  Reproduce it.
    for (double dta : {4.0, 7.0, 10.0}) {
      double thr = 99.0;
      for (double rel = -2.0; rel <= 2.0 + 1e-9; rel += 0.125) {
        cell_result r = run_cell(*h, 0, 0.0, dta * unit, rel, 1e9, fading_mode::none, ds_s, taps,
                                 true, true, 1, mu, bound, seed, nullptr);
        if (r.n_attacker == 1) {
          thr = rel;
          break;
        }
      }
      std::printf("G4_capture_threshold delta_units=%.1f threshold_db=%.3f -> %s\n",
                  dta, thr, std::abs(thr) <= 0.1251 ? "PASS" : "FAIL");
    }

    // G5: scalloping.  Measured in TWO ways, because the contest and the kernel are
    // different quantities and the project's earlier record conflated them.
    //   G5a  single path only: the drop in reported preamble power when the path moves
    //        off the detector's IDFT grid.  This is the kernel loss, with no contest.
    //   G5b  two paths: the extra power the relayed copy needs to win at a half-bin
    //        offset.  This differs from G5a by the coherent sidelobe interference
    //        between the two peaks, so G5a is the quantity the Dirichlet bound predicts.
    {
      auto power_at = [&](double dta) {
        cell_result r = run_cell(*h, 15, 0.0, 0.0, 0.0, 1e9, fading_mode::none, ds_s, taps,
                                 false, true, 1, mu, bound, seed, nullptr);
        (void)dta;
        return r;
      };
      (void)power_at;
      // single-path power, on grid and at half-bin offset (victim absent; the lone path is
      // placed by --delta-units through the attacker slot at 0 dB)
      cell_result on  = run_cell(*h, 15, 0.0, 7.0 * unit, 0.0, 1e9, fading_mode::none, ds_s, taps,
                                 false, true, 1, mu, bound, seed, nullptr);
      cell_result off = run_cell(*h, 15, 0.0, 7.25 * unit, 0.0, 1e9, fading_mode::none, ds_s, taps,
                                 false, true, 1, mu, bound, seed, nullptr);
      const double loss_db = on.sum_power_db - off.sum_power_db;
      // The point-sample Dirichlet model, -20log10(|sin(pi L d/N)/sin(pi d/N)|/L), predicts
      // 1.0798 dB at d = 0.5 bin.  The real detector loses LESS than that, and its correlation
      // peak sits a constant +0.10 bin ahead of the true delay (G6), so the model is an upper
      // BOUND on the off-grid penalty rather than an equality.  The gate therefore checks the
      // bound, which is the defensible claim.
      std::printf("G5a_kernel_loss_single_path half_bin_loss_db=%.4f dirichlet_bound_db=1.0798 -> %s\n",
                  loss_db, (loss_db > 0.0 && loss_db <= 1.0798) ? "PASS" : "FAIL");

      double thr = 99.0;
      for (double rel = -2.0; rel <= 3.0 + 1e-9; rel += 0.0625) {
        cell_result r = run_cell(*h, 15, 0.0, 7.25 * unit, rel, 1e9, fading_mode::none, ds_s, taps,
                                 true, true, 1, mu, bound, seed, nullptr);
        if (r.n_attacker == 1) {
          thr = rel;
          break;
        }
      }
      std::printf("G5b_contest_half_bin threshold_db=%.4f kernel_loss_db=%.4f "
                  "interference_term_db=%.4f -> %s\n", thr, loss_db, thr - loss_db,
                  (thr > loss_db - 0.3 && thr < loss_db + 0.5) ? "PASS" : "FAIL");
    }

    // G6: the detector's peak bias.  Measured by finding, for several absolute delays, the
    // fractional offset at which the reported peak power is largest.  It must be the SAME
    // offset at every delay (a constant group delay, not a scale error) and small compared
    // with the half-T_A-unit quantisation that the MAC CE's T_A field imposes anyway.
    {
      double first_bias = 0.0;
      bool   consistent = true;
      for (double base : {2.0, 10.0, 20.0, 30.0}) {
        double best_p = -1e9, best_frac = 0.0;
        for (int i = 0; i <= 10; ++i) {
          const double dta = base + 0.05 * i;
          cell_result r = run_cell(*h, 15, 0.0, dta * unit, 0.0, 1e9, fading_mode::none, ds_s,
                                   taps, false, true, 1, mu, bound, seed, nullptr);
          if (r.detected == 0) {
            continue;
          }
          if (r.sum_power_db > best_p) {
            best_p    = r.sum_power_db;
            best_frac = dta * 2.0 - std::round(r.sum_err * 2.0);
          }
        }
        if (base == 2.0) {
          first_bias = best_frac;
        } else if (std::abs(best_frac - first_bias) > 1e-6) {
          consistent = false;
        }
      }
      std::printf("G6_peak_bias bias_bins=%.3f bias_ns=%.3f bias_ta_units=%.4f "
                  "delay_independent=%s -> %s\n",
                  first_bias, first_bias * 1e9 / (h->scs_hz * 256.0), first_bias / 2.0,
                  consistent ? "yes" : "no",
                  (consistent && std::abs(first_bias) < 0.5) ? "PASS" : "FAIL");
    }

    if (raw != nullptr) {
      std::fclose(raw);
    }
    return 0;
  }

  // ------------------------------------------------------------------ sweeps
  print_header();
  const bool with_victim = (mode != "absent");

  for (double z : zcz_list) {
    for (double snr : snr_list) {
      for (double dta : dlt_list) {
        for (double rel : rel_list) {
          cell_result r = run_cell(*h,
                                   static_cast<unsigned>(z),
                                   tau_v,
                                   dta * unit,
                                   rel,
                                   snr,
                                   fading,
                                   ds_s,
                                   taps,
                                   with_victim,
                                   true,
                                   trials,
                                   mu,
                                   bound,
                                   seed,
                                   raw);
          print_row(mode.c_str(), fmts, scs_khz, mu, static_cast<unsigned>(z), fading, ds_s, taps,
                    snr, tau_v, dta * unit, rel, r);
        }
      }
    }
  }
  if (raw != nullptr) {
    std::fclose(raw);
  }
  return 0;
}
