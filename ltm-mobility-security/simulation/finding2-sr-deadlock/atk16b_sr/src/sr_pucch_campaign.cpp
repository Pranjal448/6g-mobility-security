// Out-of-tree driver: does a scheduling request survive a corrupted timing advance?
//
// Finding 1 leaves the UE applying a timing advance that is wrong by a known number of
// T_A units.  Finding 2 needs the UE's scheduling requests to go unanswered until
// SR_COUNTER reaches sr-TransMax.  This driver closes the gap between the two by asking
// srsRAN's own PUCCH Format 0 detector -- the receiver that actually recovers a positive
// scheduling request -- whether it still detects the request at a given timing error.
//
// The uplink is modelled in the time domain so that inter-symbol interference is real:
// every OFDM symbol is built, cyclic-prefixed, passed through a channel, and re-windowed
// at the receiver with an offset, exactly as a misaligned UE would be received.  Nothing
// in srsRAN is modified; the detector is linked as built.
//
// Geometry of the timing error, with the gNB's window fixed:
//   e > 0  the UE over-advances (the attacker INFLATED the stored TA), so the signal
//          arrives EARLY.  The cyclic prefix gives no protection on this side; the
//          window runs into the following symbol.
//   e < 0  the UE under-advances, the signal arrives LATE, and the prefix absorbs it
//          up to its own length.
// Finding 1 inflates the stored value, so e > 0 is the operative side.

#include "srsran/phy/support/resource_grid_reader.h"
#include "srsran/phy/upper/channel_processors/pucch/pucch_detector.h"
#include "srsran/phy/upper/pucch_helper.h"
#include "srsran/phy/upper/sequence_generators/sequence_generator_factories.h"
#include "srsran/ran/cyclic_prefix.h"
#include "srsran/ran/slot_point.h"
#include "srsran/srslog/srslog.h"

#include "../../../../build_env/srsran_full/lib/phy/upper/channel_processors/pucch/pucch_detector_format0.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstring>
#include <fftw3.h>
#include <iostream>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>

using namespace srsran;

// ---------------------------------------------------------------- OFDM geometry
// One T_A unit is 16*64*Tc/2^mu and one OFDM symbol (without prefix) is 2048*64*Tc/2^mu,
// so a unit is exactly 1/128 of a symbol.  With a 2048-point transform that is 16 samples,
// and the normal cyclic prefix of 144*64*Tc/2^mu is 144 samples -- nine units, at every
// numerology.  The same algebra is eq:cp9 in the report.
static constexpr unsigned NFFT          = 2048;
static constexpr unsigned NCP           = 144;
static constexpr unsigned SAMP_PER_UNIT = NFFT / 128; // 16
static constexpr unsigned NSYMB         = 14;
static constexpr unsigned NRB           = 51;        // 20 MHz at 30 kHz
static constexpr unsigned NSUBC         = NRB * NRE; // 612

// ---------------------------------------------------------------- minimal grid reader
// The Format 0 detector reads one PRB of one or two symbols through the span<cf_t> overload.
// Only that path is exercised; the rest of the interface is present to satisfy the ABI.
class freq_grid : public resource_grid_reader
{
public:
  freq_grid(unsigned nof_ports_) : nof_ports(nof_ports_), re(nof_ports_ * NSYMB * NSUBC, cf_t(0.0F, 0.0F)) {}

  cf_t&       at(unsigned port, unsigned l, unsigned k) { return re[(port * NSYMB + l) * NSUBC + k]; }
  const cf_t& at(unsigned port, unsigned l, unsigned k) const { return re[(port * NSYMB + l) * NSUBC + k]; }

  unsigned get_nof_ports() const override { return nof_ports; }
  unsigned get_nof_subc() const override { return NSUBC; }
  unsigned get_nof_symbols() const override { return NSYMB; }
  bool     is_empty(unsigned) const override { return false; }
  bool     is_empty() const override { return false; }

  void get(span<cf_t> symbols, unsigned port, unsigned l, unsigned k_init, unsigned stride = 1) const override
  {
    for (unsigned i = 0, n = symbols.size(); i != n; ++i) {
      symbols[i] = at(port, l, k_init + i * stride);
    }
  }

  span<cf_t> get(span<cf_t>, unsigned, unsigned, unsigned, const bounded_bitset<MAX_RB * NRE>&) const override
  {
    srsran_terminate("unused");
  }
  span<cbf16_t> get(span<cbf16_t>, unsigned, unsigned, unsigned, const bounded_bitset<MAX_RB * NRE>&) const override
  {
    srsran_terminate("unused");
  }
  void get(span<cbf16_t>, unsigned, unsigned, unsigned) const override { srsran_terminate("unused"); }
  span<const cbf16_t> get_view(unsigned, unsigned) const override { srsran_terminate("unused"); }

private:
  unsigned          nof_ports;
  std::vector<cf_t> re;
};

// ---------------------------------------------------------------- channel
struct chan_tap {
  int   delay_samples;
  float amplitude;
};

// TDL-C style profile, normalised to unit total power, quantised onto the sample grid.
static std::vector<chan_tap> make_pdp(float ds_ns, unsigned nof_taps, float scs_khz, std::mt19937& rng)
{
  // Sample interval: one OFDM symbol of 1/(scs) seconds spans NFFT samples.
  const double samp_s = 1.0 / (static_cast<double>(scs_khz) * 1e3 * NFFT);
  std::vector<chan_tap>               taps;
  std::exponential_distribution<float> delay_dist(1.0F);
  std::normal_distribution<float>      g(0.0F, 1.0F);

  std::vector<double> d(nof_taps), p(nof_taps);
  double              psum = 0.0;
  for (unsigned i = 0; i != nof_taps; ++i) {
    d[i] = (i == 0) ? 0.0 : delay_dist(rng) * ds_ns * 1e-9;
    p[i] = std::exp(-d[i] / (ds_ns * 1e-9));
    psum += p[i];
  }
  for (unsigned i = 0; i != nof_taps; ++i) {
    const float amp = static_cast<float>(std::sqrt(p[i] / psum));
    taps.push_back({static_cast<int>(std::lround(d[i] / samp_s)), amp});
  }
  return taps;
}

// ---------------------------------------------------------------- argument helpers
static std::vector<float> parse_list(const std::string& s)
{
  std::vector<float> v;
  std::stringstream  ss(s);
  std::string        tok;
  while (std::getline(ss, tok, ',')) {
    if (!tok.empty()) {
      v.push_back(std::stof(tok));
    }
  }
  return v;
}

int main(int argc, char** argv)
{
  srslog::init();

  // Defaults: 30 kHz, one receive port, two PUCCH symbols, a loaded band, and srsRAN's
  // own window offset of half a prefix (see the early/late asymmetry in the appendix).
  float       scs_khz      = 30.0F;
  unsigned    nof_ports    = 1;
  unsigned    nof_symbols  = 2;
  unsigned    start_symbol = 12;
  unsigned    trials       = 2000;
  unsigned    seed         = 20261115;
  bool        loaded_band  = true;
  // Window offset ahead of the useful part, in T_A units.  Nominal is zero: the receiver
  // transforms the N_FFT samples that follow the prefix.  A non-zero offset is a cyclic
  // rotation, which costs coherence across the twelve PUCCH subcarriers, so unlike the
  // data channel the control channel cannot buy early-side margin this way.
  float       win_units    = 0.0F;
  std::string fading       = "rayleigh";
  float       ds_ns        = 300.0F;
  unsigned    nof_taps     = 20;
  std::string snr_list     = "10";
  std::string err_list     = "-12,-10,-9,-8,-7,-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,6,7,8,9,10,12";
  std::string mode         = "grid";

  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto        nxt = [&]() { return std::string(argv[++i]); };
    if (a == "--scs") { scs_khz = std::stof(nxt()); }
    else if (a == "--ports") { nof_ports = std::stoul(nxt()); }
    else if (a == "--nof-sym") { nof_symbols = std::stoul(nxt()); }
    else if (a == "--start-sym") { start_symbol = std::stoul(nxt()); }
    else if (a == "--trials") { trials = std::stoul(nxt()); }
    else if (a == "--seed") { seed = std::stoul(nxt()); }
    else if (a == "--empty-band") { loaded_band = false; }
    else if (a == "--win-units") { win_units = std::stof(nxt()); }
    else if (a == "--fading") { fading = nxt(); }
    else if (a == "--ds-ns") { ds_ns = std::stof(nxt()); }
    else if (a == "--nof-taps") { nof_taps = std::stoul(nxt()); }
    else if (a == "--snr-list") { snr_list = nxt(); }
    else if (a == "--err-list") { err_list = nxt(); }
    else if (a == "--mode") { mode = nxt(); }
    else { std::cerr << "unknown argument " << a << "\n"; return 1; }
  }

  // ------------------------------------------------------------ detector, as srsRAN builds it
  auto prg_factory      = create_pseudo_random_generator_sw_factory();
  auto lpg_factory      = create_low_papr_sequence_generator_sw_factory();
  auto lpc_factory      = create_low_papr_sequence_collection_sw_factory(lpg_factory);
  std::array<float, NRE> alphas;
  std::generate(alphas.begin(), alphas.end(), [n = 0U]() mutable {
    return (TWOPI * static_cast<float>(n++) / static_cast<float>(NRE));
  });
  auto collection_tx = lpc_factory->create(1, 0, alphas);
  auto collection_rx = lpc_factory->create(1, 0, alphas);

  pucch_detector_format0 detector(prg_factory->create(), std::move(collection_rx));
  pucch_helper           tx_helper(prg_factory->create());

  // ------------------------------------------------------------ fixed configuration
  const unsigned          mu_from_scs = static_cast<unsigned>(std::lround(std::log2(scs_khz / 15.0F)));
  const slot_point        slot(mu_from_scs, 0);
  const cyclic_prefix     cp(cyclic_prefix::NORMAL);
  const unsigned          n_id                 = 41;
  const unsigned          initial_cyclic_shift = 0;
  const unsigned          pucch_prb            = 0;

  pucch_detector::format0_configuration cfg;
  cfg.slot                 = slot;
  cfg.cp                   = cp;
  cfg.starting_prb         = pucch_prb;
  cfg.second_hop_prb       = std::nullopt;
  cfg.start_symbol_index   = start_symbol;
  cfg.nof_symbols          = nof_symbols;
  cfg.initial_cyclic_shift = initial_cyclic_shift;
  cfg.n_id                 = n_id;
  cfg.nof_harq_ack         = 0;    // positive scheduling request only
  cfg.sr_opportunity       = true;
  for (unsigned p = 0; p != nof_ports; ++p) {
    cfg.ports.push_back(static_cast<uint8_t>(p));
  }

  // Transmit sequence: the same low-PAPR sequence the detector correlates against, with
  // the cyclic shift m_cs = 0 that TS 38.213 Section 9.2.4 assigns to a positive request.
  const auto uv = pucch_helper::compute_group_sequence(pucch_group_hopping::NEITHER, n_id);

  // ------------------------------------------------------------ transform plans
  std::vector<std::complex<float>> td_in(NFFT), td_out(NFFT);
  fftwf_plan plan_ifft = fftwf_plan_dft_1d(NFFT,
                                           reinterpret_cast<fftwf_complex*>(td_in.data()),
                                           reinterpret_cast<fftwf_complex*>(td_out.data()),
                                           FFTW_BACKWARD,
                                           FFTW_MEASURE);
  fftwf_plan plan_fft  = fftwf_plan_dft_1d(NFFT,
                                          reinterpret_cast<fftwf_complex*>(td_in.data()),
                                          reinterpret_cast<fftwf_complex*>(td_out.data()),
                                          FFTW_FORWARD,
                                          FFTW_MEASURE);

  const float          norm = 1.0F / std::sqrt(static_cast<float>(NFFT));
  const unsigned       slot_len = NSYMB * (NFFT + NCP);
  std::mt19937         rng(seed);
  std::normal_distribution<float> gauss(0.0F, 1.0F);

  // subcarrier k of the active band -> transform bin
  auto bin_of = [](unsigned k) { return (k + NFFT - NSUBC / 2) % NFFT; };

  const auto snrs = parse_list(snr_list);
  const auto errs = parse_list(err_list);

  if (mode == "gates") {
    // Geometry checks that must hold before any figure is taken.
    std::cout << "check cp_units " << (NCP / SAMP_PER_UNIT)
              << (NCP % SAMP_PER_UNIT == 0 && NCP / SAMP_PER_UNIT == 9 ? " PASS" : " FAIL") << "\n";
    std::cout << "check samp_per_unit " << SAMP_PER_UNIT << (SAMP_PER_UNIT == 16 ? " PASS" : " FAIL") << "\n";
    std::cout << "check table_threshold "
              << (nof_ports * nof_symbols) << " seq 1\n";
    return 0;
  }

  std::cout << "scs_khz,ports,nof_sym,band,win_units,fading,ds_ns,snr_db,err_units,trials,p_sr,mean_metric\n";

  for (float snr_db : snrs) {
    const float noise_var = std::pow(10.0F, -snr_db / 10.0F);
    const float noise_sd  = std::sqrt(noise_var / 2.0F);

    for (float err_units : errs) {
      // Window start displacement in samples.  Positive err means the signal arrives early,
      // so relative to the signal the fixed window begins later.
      const int shift = static_cast<int>(std::lround(err_units * SAMP_PER_UNIT));

      unsigned detected   = 0;
      double   metric_sum = 0.0;

      for (unsigned t = 0; t != trials; ++t) {
        // ---------------- build the transmitted slot in the frequency domain
        std::vector<std::vector<cf_t>> tx_grid(NSYMB, std::vector<cf_t>(NSUBC, cf_t(0.0F, 0.0F)));
        if (loaded_band) {
          for (unsigned l = 0; l != NSYMB; ++l) {
            for (unsigned k = 0; k != NSUBC; ++k) {
              const float re_ = (rng() & 1U) ? 0.70710678F : -0.70710678F;
              const float im_ = (rng() & 1U) ? 0.70710678F : -0.70710678F;
              tx_grid[l][k]   = cf_t(re_, im_);
            }
          }
        }
        // Overwrite the PUCCH resource with the request.
        for (unsigned i = 0; i != nof_symbols; ++i) {
          const unsigned l     = start_symbol + i;
          const unsigned alpha = tx_helper.get_alpha_index(slot, cp, n_id, l, initial_cyclic_shift, 0);
          span<const cf_t> seq = collection_tx->get(uv.first, uv.second, alpha);
          for (unsigned k = 0; k != NRE; ++k) {
            tx_grid[l][pucch_prb * NRE + k] = seq[k];
          }
        }

        // ---------------- to the time domain, with a cyclic prefix on every symbol
        std::vector<cf_t> stream(slot_len, cf_t(0.0F, 0.0F));
        for (unsigned l = 0; l != NSYMB; ++l) {
          std::fill(td_in.begin(), td_in.end(), cf_t(0.0F, 0.0F));
          for (unsigned k = 0; k != NSUBC; ++k) {
            td_in[bin_of(k)] = tx_grid[l][k];
          }
          fftwf_execute(plan_ifft);
          const unsigned base = l * (NFFT + NCP);
          for (unsigned n = 0; n != NCP; ++n) {
            stream[base + n] = td_out[NFFT - NCP + n] * norm;
          }
          for (unsigned n = 0; n != NFFT; ++n) {
            stream[base + NCP + n] = td_out[n] * norm;
          }
        }

        // ---------------- channel
        std::vector<chan_tap> taps;
        if (fading == "none") {
          taps = {{0, 1.0F}};
        } else if (fading == "rayleigh") {
          taps = {{0, 1.0F}};
        } else {
          taps = make_pdp(ds_ns, nof_taps, scs_khz, rng);
        }

        freq_grid grid(nof_ports);
        for (unsigned p = 0; p != nof_ports; ++p) {
          std::vector<cf_t> rx(slot_len + 4 * NFFT, cf_t(0.0F, 0.0F));
          for (const auto& tap : taps) {
            cf_t h = cf_t(tap.amplitude, 0.0F);
            if (fading != "none") {
              h = cf_t(gauss(rng), gauss(rng)) * (tap.amplitude * 0.70710678F);
            }
            for (unsigned n = 0; n != slot_len; ++n) {
              rx[n + tap.delay_samples] += stream[n] * h;
            }
          }
          for (auto& s : rx) {
            s += cf_t(gauss(rng), gauss(rng)) * noise_sd;
          }

          // ---------------- receiver: window each PUCCH symbol and transform back
          for (unsigned i = 0; i != nof_symbols; ++i) {
            const unsigned l    = start_symbol + i;
            const int      w0   = static_cast<int>(l * (NFFT + NCP) + NCP);
            const int      wofs = static_cast<int>(std::lround(win_units * SAMP_PER_UNIT));
            const int      start = w0 + shift - wofs;
            std::fill(td_in.begin(), td_in.end(), cf_t(0.0F, 0.0F));
            for (unsigned n = 0; n != NFFT; ++n) {
              const int idx = start + static_cast<int>(n);
              if (idx >= 0 && idx < static_cast<int>(rx.size())) {
                td_in[n] = rx[idx];
              }
            }
            fftwf_execute(plan_fft);
            for (unsigned k = 0; k != NSUBC; ++k) {
              grid.at(p, l, k) = td_out[bin_of(k)] * norm;
            }
          }
        }

        // ---------------- srsRAN's own detector decides
        const auto res = detector.detect(grid, cfg);
        metric_sum += std::pow(10.0, res.second.get_sinr_dB().value_or(-99.0) / 10.0);
        if (res.first.get_status() == uci_status::valid) {
          const auto sr = res.first.get_sr_bits();
          if (!sr.empty() && sr[0] == 1U) {
            ++detected;
          }
        }
      }

      std::cout << scs_khz << "," << nof_ports << "," << nof_symbols << ","
                << (loaded_band ? "loaded" : "empty") << "," << win_units << "," << fading << ","
                << (fading == "pdp" ? ds_ns : 0.0F) << "," << snr_db << "," << err_units << ","
                << trials << "," << (static_cast<double>(detected) / trials) << ","
                << (metric_sum / trials) << "\n";
      std::cout.flush();
    }
  }

  fftwf_destroy_plan(plan_ifft);
  fftwf_destroy_plan(plan_fft);
  return 0;
}
