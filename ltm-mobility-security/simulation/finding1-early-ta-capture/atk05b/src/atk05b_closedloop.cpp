/*
 * ATK-05b full campaign -- Leg R: can a real receiver RE-TRACK the corrupted timing?
 *
 * The 2026-11-11 rebuild (08_final_factcheck/ATK05_SIMULATION_REBUILD.md) left one item at the
 * top of its own "what remains untested" list, and labelled it attacker-favourable:
 *
 *     "Every number here holds the FFT window fixed for the whole slot.  Real receivers
 *      re-estimate timing from DM-RS and re-position the window [...]  The fixed-window model
 *      is therefore pessimistic, i.e. attacker-favourable, which is the wrong direction for a
 *      feasibility claim.  This is the single highest-value thing left to close."
 *
 * This driver closes it, using srsRAN's own DM-RS time-alignment estimator (the same one a
 * deployed gNB uses to generate Timing Advance Commands) in a two-pass loop:
 *
 *   pass 1  demodulate with the receiver's nominal window, estimate the channel, and read the
 *           estimator's reported time alignment;
 *   pass 2  quantise that reading to a whole Timing Advance unit -- which is all a TA Command
 *           can convey (TS 38.213 clause 4.2) -- re-read the SAME received samples with the
 *           window moved by that amount, and re-estimate and re-equalise.
 *
 * Pass 2 is deliberately OPTIMISTIC about the receiver: it lets the gNB correct the very slot it
 * measured, which a real gNB cannot do for the first PUSCH of a RACH-less LTM cell switch
 * (the correction would have to travel back to the UE in a MAC CE first).  If even this
 * optimistic loop cannot recover the slot, no realistic closed loop can.
 *
 * The question it answers is therefore: does the DM-RS estimator's unambiguous range cover the
 * timing error at which the slot stops decoding?  If it does, ATK-05b's physical-layer half is
 * self-correcting and the damage claim must come from somewhere else.  If it does not, the
 * corrupted TA is outside the receiver's own ability to measure it, and the fixed-window
 * boundary stands.
 *
 * Derived from 08_final_factcheck/sim_rebuild/src/ta_evm_sweep.cpp (same channel, same srsRAN
 * components, same sign convention), with the closed loop and the per-trial estimator statistics
 * added.  No file in the srsRAN tree is touched.
 *
 * Original header follows.
 * ------------------------------------------------------------------------------------------
 * Leg 1: OFDM symbol-level timing-error sweep.
 *
 * Measures post-equalisation EVM of a PUSCH-like slot as a function of a controlled
 * uplink timing error, in BOTH directions, using srsRAN's UNMODIFIED
 *   - ofdm_slot_modulator / ofdm_slot_demodulator   (lib/phy/lower/modulation)
 *   - dmrs_pusch_estimator + port_channel_estimator (lib/phy/upper/signal_processors)
 *   - channel_equalizer (ZF)                        (lib/phy/upper/equalization)
 *   - modulation_mapper                             (lib/phy/upper/channel_modulation)
 *
 * SIGN CONVENTION (the whole point of this rebuild):
 *   ta_units > 0  ==  the receiver reads its window LATER than the signal's true
 *                     slot start  ==  the signal ARRIVES EARLY  ==  the stored TA
 *                     was TOO LARGE  ==  the relay/ATK-05 direction.
 *   ta_units < 0  ==  the signal ARRIVES LATE (the direction a cyclic prefix exists
 *                     to absorb).
 * The CSV carries an explicit `direction` column so the sign can never be lost again.
 *
 * Channel: TR 38.901 TDL profiles (Tables 7.7.2-1 / -3), delays scaled per Clause 7.7.3.
 * Relay model: the relayed copy is ADDED to the direct path, never substituted.
 *
 * No file in the srsRAN tree is touched; this driver lives outside it and links
 * against the libraries already built in srsran_full/build.
 */

#include "srsran/phy/generic_functions/generic_functions_factories.h"
#include "srsran/phy/lower/modulation/modulation_factories.h"
#include "srsran/phy/support/resource_grid.h"
#include "srsran/phy/support/resource_grid_reader.h"
#include "srsran/phy/support/resource_grid_writer.h"
#include "srsran/phy/support/support_factories.h"
#include "srsran/phy/upper/channel_modulation/channel_modulation_factories.h"
#include "srsran/phy/upper/equalization/equalization_factories.h"
#include "srsran/phy/upper/equalization/modular_ch_est_list.h"
#include "srsran/phy/upper/sequence_generators/sequence_generator_factories.h"
#include "srsran/phy/upper/signal_processors/channel_estimator/factories.h"
#include "srsran/phy/upper/signal_processors/pusch/factories.h"
#include "srsran/phy/support/time_alignment_estimator/time_alignment_estimator_factories.h"
#include "srsran/support/executors/task_executor.h"

// Private srsRAN header, included (not modified) so that the transmitter emits exactly the
// same DM-RS sequence that srsRAN's own estimator regenerates internally.
#include "../../../../../build_env/srsran_full/lib/phy/upper/signal_processors/dmrs_helper.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdio>
#include <cstring>
#include <map>
#include <numeric>
#include <random>
#include <string>
#include <vector>

using namespace srsran;

// ---------------------------------------------------------------------------------------
// TR 38.901 tapped delay line profiles.  Normalised delays and powers transcribed verbatim
// from /run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/01_specs_txt/38.901_38901-j50.txt
//   TDL-A : Table 7.7.2-1, lines 2366-2388   (23 taps, all Rayleigh)
//   TDL-C : Table 7.7.2-3, lines 2426-2450   (24 taps, all Rayleigh)
// Delay scaling: Clause 7.7.3 eq (7.7-1),  tau_n = tau_norm_n * DS_desired.
// ---------------------------------------------------------------------------------------
struct tdl_profile {
  const char*                name;
  std::vector<double>        norm_delay;
  std::vector<double>        power_db;
};

static const tdl_profile TDL_A = {
    "TDL-A",
    {0.0000, 0.3819, 0.4025, 0.5868, 0.4610, 0.5375, 0.6708, 0.5750, 0.7618, 1.5375, 1.8978, 2.2242,
     2.1718, 2.4942, 2.5119, 3.0582, 4.0810, 4.4579, 4.5695, 4.7966, 5.0066, 5.3043, 9.6586},
    {-13.4, 0.0, -2.2, -4.0, -6.0, -8.2, -9.9, -10.5, -7.5, -15.9, -6.6, -16.7,
     -12.4, -15.2, -10.8, -11.3, -12.7, -16.2, -18.3, -18.9, -16.6, -19.9, -29.7}};

static const tdl_profile TDL_C = {
    "TDL-C",
    {0.0000, 0.2099, 0.2219, 0.2329, 0.2176, 0.6366, 0.6448, 0.6560, 0.6584, 0.7935, 0.8213, 0.9336,
     1.2285, 1.3083, 2.1704, 2.7105, 4.2589, 4.6003, 5.4902, 5.6077, 6.3065, 6.6374, 7.0427, 8.6523},
    {-4.4, -1.2, -3.5, -5.2, -2.5, 0.0, -2.2, -3.9, -7.4, -7.1, -10.7, -11.1,
     -5.1, -6.8, -8.7, -13.2, -13.9, -13.9, -15.8, -17.1, -16.0, -15.7, -21.6, -22.8}};

// ---------------------------------------------------------------------------------------
// Minimal inline task executor (the DM-RS estimator factory wants one).
// ---------------------------------------------------------------------------------------
class inline_executor : public task_executor
{
public:
  bool execute(unique_task task) override
  {
    task();
    return true;
  }
  bool defer(unique_task task) override
  {
    task();
    return true;
  }
};

class noop_notifier : public dmrs_pusch_estimator_notifier
{
public:
  void on_estimation_complete() override {}
};

// ---------------------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------------------
struct options {
  unsigned    mu          = 1;      // numerology: 0 (15 kHz), 1 (30 kHz), 2 (60 kHz)
  unsigned    dft_size    = 1024;   // fixed across numerologies => TA unit = dft/128 samples
  unsigned    nof_prb     = 25;     // chosen per mu to match occupied bandwidth
  std::string profile     = "TDL-C";
  double      ds_ns       = 300.0;  // TR 38.901 Table 7.7.3-1 scaling
  std::string mod         = "QPSK";
  double      snr_db      = 20.0;
  double      win_offset  = 0.5;    // srsRAN deployed uplink value (dft_window_offset)
  int         ta_min      = -40;
  int         ta_max      = 40;
  unsigned    trials      = 200;
  unsigned    seed        = 1;
  std::string csv         = "";
  // Relay (added-path) model.
  bool   relay          = false;
  double relay_delay_ta = 0.0;   // relayed-copy excess delay, in TA units
  double relay_power_db = 0.0;   // relayed-copy power relative to the direct path
  bool   awgn_only      = false; // disable the TDL channel (single flat path), for gates
  // srsRAN channel-estimator strategies. Defaults are srsRAN's own gNB defaults
  // (apps/units/flexible_o_du/o_du_low/du_low_config.h: fd "filter", td "average").
  std::string fd_strategy = "filter";  // filter | mean | none
  std::string td_strategy = "average"; // average | interpolate
  // Leg R: run the two-pass closed loop (estimate the time alignment from DM-RS, quantise it to
  // a whole TA unit, re-read the same samples with the window moved, re-estimate, re-equalise).
  bool closed_loop = false;
};

static void usage(const char* p)
{
  std::printf(
      "usage: %s [--mu N] [--dft N] [--prb N] [--profile TDL-A|TDL-C] [--ds-ns X] [--mod QPSK|QAM16|QAM64]\n"
      "          [--snr X] [--win-offset X] [--ta-min N] [--ta-max N] [--trials N] [--seed N] [--csv F]\n"
      "          [--relay --relay-delay-ta X --relay-power-db X] [--awgn-only] [--closed-loop]\n",
      p);
}

int main(int argc, char** argv)
{
  options opt;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto        nxt = [&]() -> std::string { return (i + 1 < argc) ? argv[++i] : ""; };
    if (a == "--mu") opt.mu = std::stoul(nxt());
    else if (a == "--dft") opt.dft_size = std::stoul(nxt());
    else if (a == "--prb") opt.nof_prb = std::stoul(nxt());
    else if (a == "--profile") opt.profile = nxt();
    else if (a == "--ds-ns") opt.ds_ns = std::stod(nxt());
    else if (a == "--mod") opt.mod = nxt();
    else if (a == "--snr") opt.snr_db = std::stod(nxt());
    else if (a == "--win-offset") opt.win_offset = std::stod(nxt());
    else if (a == "--ta-min") opt.ta_min = std::stoi(nxt());
    else if (a == "--ta-max") opt.ta_max = std::stoi(nxt());
    else if (a == "--trials") opt.trials = std::stoul(nxt());
    else if (a == "--seed") opt.seed = std::stoul(nxt());
    else if (a == "--csv") opt.csv = nxt();
    else if (a == "--relay") opt.relay = true;
    else if (a == "--relay-delay-ta") opt.relay_delay_ta = std::stod(nxt());
    else if (a == "--relay-power-db") opt.relay_power_db = std::stod(nxt());
    else if (a == "--awgn-only") opt.awgn_only = true;
    else if (a == "--fd") opt.fd_strategy = nxt();
    else if (a == "--td") opt.td_strategy = nxt();
    else if (a == "--closed-loop") opt.closed_loop = true;
    else { usage(argv[0]); return 1; }
  }

  // ---------------- derived PHY parameters ----------------
  const subcarrier_spacing scs      = to_subcarrier_spacing(opt.mu);
  const unsigned           srate_hz = opt.dft_size * 15000U * (1U << opt.mu);
  const cyclic_prefix      cp       = cyclic_prefix::NORMAL;
  const unsigned           nsymb    = get_nsymb_per_slot(cp);
  const unsigned           rg_size  = opt.nof_prb * NRE;

  // TA unit: 16*64*Tc/2^mu seconds  ->  in samples at srate = dft*15k*2^mu  it is dft/128.
  const double ta_unit_s       = 16.0 * 64.0 / (480000.0 * 4096.0) / std::pow(2.0, opt.mu);
  const double ta_unit_samples = ta_unit_s * srate_hz;            // == dft_size/128
  // Ordinary OFDM CP (symbol != 0): 144*64*Tc/2^mu  ->  9 TA units exactly.
  const unsigned cp_samples_ord = cp.get_length(1, scs).to_samples(srate_hz);

  modulation_scheme modsch = modulation_scheme::QPSK;
  if (opt.mod == "QAM16") modsch = modulation_scheme::QAM16;
  else if (opt.mod == "QAM64") modsch = modulation_scheme::QAM64;
  else if (opt.mod == "QAM256") modsch = modulation_scheme::QAM256;
  const unsigned bps = get_bits_per_symbol(modsch);

  const tdl_profile& prof = (opt.profile == "TDL-A") ? TDL_A : TDL_C;

  // ---------------- srsRAN factories (all unmodified srsRAN code) ----------------
  auto dft_factory = create_dft_processor_factory_fftw_slow();
  if (!dft_factory) dft_factory = create_dft_processor_factory_generic();
  ofdm_factory_generic_configuration ofdm_cfg;
  ofdm_cfg.dft_factory  = dft_factory;
  auto mod_factory      = create_ofdm_modulator_factory_generic(ofdm_cfg);
  auto demod_factory    = create_ofdm_demodulator_factory_generic(ofdm_cfg);
  auto rg_factory       = create_resource_grid_factory();
  auto prg_factory      = create_pseudo_random_generator_sw_factory();
  auto lowpapr_factory  = create_low_papr_sequence_generator_sw_factory();
  auto ta_est_factory   = create_time_alignment_estimator_dft_factory(dft_factory);
  auto ch_est_factory   = create_port_channel_estimator_factory_sw(ta_est_factory);
  inline_executor exec;
  // srsRAN gNB defaults: apps/units/flexible_o_du/o_du_low/du_low_config.h
  //   pusch_channel_estimator_fd_strategy = "filter", td_strategy = "average"
  port_channel_estimator_fd_smoothing_strategy fd_strat =
      port_channel_estimator_fd_smoothing_strategy::filter;
  if (opt.fd_strategy == "mean") fd_strat = port_channel_estimator_fd_smoothing_strategy::mean;
  else if (opt.fd_strategy == "none") fd_strat = port_channel_estimator_fd_smoothing_strategy::none;
  port_channel_estimator_td_interpolation_strategy td_strat =
      port_channel_estimator_td_interpolation_strategy::average;
  if (opt.td_strategy == "interpolate")
    td_strat = port_channel_estimator_td_interpolation_strategy::interpolate;
  auto dmrs_est_factory = create_dmrs_pusch_estimator_factory_sw(
      prg_factory, lowpapr_factory, ch_est_factory, exec, fd_strat, td_strat, false);
  auto eq_factory  = create_channel_equalizer_generic_factory(channel_equalizer_algorithm_type::zf);
  auto mapper_fact = create_modulation_mapper_factory();

  ofdm_modulator_configuration mcfg;
  mcfg.numerology     = opt.mu;
  mcfg.bw_rb          = opt.nof_prb;
  mcfg.dft_size       = opt.dft_size;
  mcfg.cp             = cp;
  mcfg.scale          = 1.0F / std::sqrt(static_cast<float>(rg_size));
  mcfg.center_freq_Hz = 0.0;  // disable TS 38.211 5.4 phase compensation (same at tx and rx)
  auto modulator = mod_factory->create_ofdm_slot_modulator(mcfg);

  const unsigned win_off_samples =
      static_cast<unsigned>(static_cast<float>(cp_samples_ord) * static_cast<float>(opt.win_offset));
  ofdm_demodulator_configuration dcfg;
  dcfg.numerology                = opt.mu;
  dcfg.bw_rb                     = opt.nof_prb;
  dcfg.dft_size                  = opt.dft_size;
  dcfg.cp                        = cp;
  dcfg.nof_samples_window_offset = win_off_samples;
  dcfg.scale                     = 1.0F / std::sqrt(static_cast<float>(rg_size));
  dcfg.center_freq_Hz            = 0.0;
  auto demodulator = demod_factory->create_ofdm_slot_demodulator(dcfg);

  auto tx_grid  = rg_factory->create(1, nsymb, rg_size);
  auto rx_grid  = rg_factory->create(1, nsymb, rg_size);
  auto estimator = dmrs_est_factory->create();
  auto equalizer = eq_factory->create();
  auto mapper    = mapper_fact->create();
  auto prg       = prg_factory->create();

  const unsigned slot_size = modulator->get_slot_size(0);

  // DM-RS on symbols 2 and 11 (srsRAN's own pxsch_bler_test mask), TYPE1, port 1000.
  bounded_bitset<MAX_NSYMB_PER_SLOT> dmrs_mask(nsymb);
  dmrs_mask.set(2);
  dmrs_mask.set(11);
  std::vector<unsigned> data_symbols;
  for (unsigned l = 1; l < nsymb; ++l) {             // symbol 0 excluded: it carries the long CP
    if (!dmrs_mask.test(l)) data_symbols.push_back(l);
  }
  crb_bitmap rb_mask(opt.nof_prb);
  rb_mask.fill(0, opt.nof_prb);

  dmrs_pusch_estimator::configuration ecfg;
  ecfg.slot            = slot_point(opt.mu, 0);
  ecfg.sequence_config = dmrs_pusch_estimator::pseudo_random_sequence_configuration{
      .type = dmrs_type::TYPE1, .nof_tx_layers = 1, .scrambling_id = 0, .n_scid = false};
  // beta_DMRS. The estimator regenerates its pilots at the hardcoded amplitude M_SQRT1_2
  // (dmrs_pusch_estimator_impl.cpp:101) and divides the LSE by this factor, so writing the
  // DM-RS at that same amplitude with beta = 1 makes the estimate equal the channel.
  // Verified by validation gate G1 (EVM -> 0 at zero offset, flat channel, high SNR).
  ecfg.scaling      = 1.0F;
  ecfg.c_prefix     = cp;
  ecfg.symbols_mask = dmrs_mask;
  ecfg.rb_mask      = rb_mask;
  ecfg.first_symbol = 0;
  ecfg.nof_symbols  = nsymb;
  ecfg.rx_ports     = {0};

  // ---------------- build the transmit grid once per trial ----------------
  std::mt19937 rng(opt.seed);
  dynamic_bit_buffer bits(rg_size * bps);
  std::vector<cf_t>  syms(rg_size);
  // reference data symbols, per data OFDM symbol
  std::vector<std::vector<cf_t>> ref(nsymb, std::vector<cf_t>(rg_size, 0.0F));

  auto fill_tx_grid = [&]() {
    tx_grid->set_all_zero();
    resource_grid_writer& w = tx_grid->get_writer();
    // data
    for (unsigned l : data_symbols) {
      for (unsigned b = 0; b < rg_size * bps; ++b) bits.insert(rng() & 1U, b, 1);
      mapper->modulate(syms, bits, modsch);
      ref[l] = syms;
      w.put(0, l, 0, span<const cf_t>(syms));
    }
    // DM-RS: generated with srsRAN's own dmrs_sequence_generate, identical c_init to the
    // estimator (dmrs_pusch_estimator_impl.cpp:108), so tx and rx references match exactly.
    std::vector<cf_t> dmrs_seq(opt.nof_prb * dmrs_type(dmrs_type::TYPE1).nof_dmrs_per_rb());
    for (unsigned l = 0; l < nsymb; ++l) {
      if (!dmrs_mask.test(l)) continue;
      unsigned c_init = ((nsymb * 0 + l + 1) * (2 * 0 + 1) * 131072U + (2 * 0 + 0)) % 2147483648U;
      prg->init(c_init);
      dmrs_sequence_generate(dmrs_seq, *prg, M_SQRT1_2, 0,
                             dmrs_type(dmrs_type::TYPE1).nof_dmrs_per_rb(), rb_mask);
      // TYPE1 port 1000: RE pattern delta 0 -> every second subcarrier.
      std::vector<cf_t> row(rg_size, 0.0F);
      for (unsigned i = 0; i < dmrs_seq.size(); ++i) row[2 * i] = dmrs_seq[i];
      w.put(0, l, 0, span<const cf_t>(row));
    }
  };

  // ---------------- channel ----------------
  // Taps quantised to the sample grid; gains Rayleigh (CN(0, p_n)) drawn per trial, static
  // within the slot (block fading, no Doppler -- stated as a scope limit).
  std::normal_distribution<float> gauss(0.0F, std::sqrt(0.5F));
  struct tap { unsigned d; double p_lin; };
  std::vector<tap> taps;
  if (opt.awgn_only) {
    taps.push_back({0, 1.0});
  } else {
    std::map<unsigned, double> acc;
    for (size_t n = 0; n < prof.norm_delay.size(); ++n) {
      double   tau_s = prof.norm_delay[n] * opt.ds_ns * 1e-9;
      unsigned d     = static_cast<unsigned>(std::llround(tau_s * srate_hz));
      acc[d] += std::pow(10.0, prof.power_db[n] / 10.0);
    }
    double tot = 0.0;
    for (auto& kv : acc) tot += kv.second;
    for (auto& kv : acc) taps.push_back({kv.first, kv.second / tot});
  }
  unsigned chan_len = 0;
  for (const tap& t : taps) chan_len = std::max(chan_len, t.d + 1);
  const unsigned relay_delay_samples =
      static_cast<unsigned>(std::llround(opt.relay_delay_ta * ta_unit_samples));
  const double relay_gain = std::pow(10.0, opt.relay_power_db / 20.0);
  if (opt.relay) chan_len += relay_delay_samples;

  // ---------------- noise calibration (self-calibrating validation gate) ----------------
  // Push unit-variance white noise through srsRAN's own demodulator and measure the
  // resulting per-RE power.  This converts a requested per-RE SNR into the time-domain
  // noise variance exactly, with no analytic assumption about the scale factors.
  double noise_gain_per_re = 0.0;
  {
    std::vector<cf_t> buf(slot_size);
    std::mt19937      r2(12345);
    std::normal_distribution<float> g(0.0F, std::sqrt(0.5F));
    double acc = 0.0; unsigned cnt = 0;
    for (unsigned it = 0; it < 20; ++it) {
      for (cf_t& s : buf) s = {g(r2), g(r2)};
      rx_grid->set_all_zero();
      demodulator->demodulate(rx_grid->get_writer(), buf, 0, 0);
      std::vector<cf_t> row(rg_size);
      for (unsigned l : data_symbols) {
        rx_grid->get_reader().get(row, 0, l, 0);
        for (const cf_t& v : row) { acc += std::norm(v); ++cnt; }
      }
    }
    noise_gain_per_re = acc / cnt;
  }
  // Clean per-RE signal power through the same chain (should equal the constellation power).
  double sig_power_per_re = 0.0;
  {
    fill_tx_grid();
    std::vector<cf_t> buf(slot_size);
    modulator->modulate(buf, tx_grid->get_reader(), 0, 0);
    rx_grid->set_all_zero();
    demodulator->demodulate(rx_grid->get_writer(), buf, 0, 0);
    std::vector<cf_t> row(rg_size);
    double acc = 0.0; unsigned cnt = 0;
    for (unsigned l : data_symbols) {
      rx_grid->get_reader().get(row, 0, l, 0);
      for (const cf_t& v : row) { acc += std::norm(v); ++cnt; }
    }
    sig_power_per_re = acc / cnt;
  }

  std::fprintf(stderr,
               "# mu=%u scs=%ukHz dft=%u srate=%.3f MHz prb=%u rg=%u slot=%u samples\n"
               "# TA unit = %.4f ns = %.1f samples | ordinary CP = %u samples = %.2f TA units\n"
               "# dft_window_offset=%.2f -> nof_samples_window_offset=%u (%.2f TA units)\n"
               "# profile=%s DS=%.1f ns taps=%zu (span %u samples) mod=%s fd=%s td=%s\n"
               "# noise_gain_per_RE=%.6e clean_sig_power_per_RE=%.6e\n",
               opt.mu, scs_to_khz(scs), opt.dft_size, srate_hz / 1e6, opt.nof_prb, rg_size, slot_size,
               ta_unit_s * 1e9, ta_unit_samples, cp_samples_ord, cp_samples_ord / ta_unit_samples,
               opt.win_offset, win_off_samples, win_off_samples / ta_unit_samples,
               opt.awgn_only ? "AWGN-flat" : prof.name, opt.ds_ns, taps.size(), chan_len,
               opt.mod.c_str(), opt.fd_strategy.c_str(), opt.td_strategy.c_str(),
               noise_gain_per_re, sig_power_per_re);

  std::FILE* out = opt.csv.empty() ? stdout : std::fopen(opt.csv.c_str(), "w");
  std::fprintf(out,
               "mu,scs_khz,dft,prb,profile,ds_ns,mod,snr_db,win_offset,fd,td,relay,relay_delay_ta,"
               "relay_power_db,ta_units,direction,ta_ns,trials,evm_mean,evm_std,evm_p90,"
               "evm_snr_db_mean,est_snr_db_mean,ta_est_ns_mean,ta_est_ns_sd,"
               "ta_est_units_mean,ta_est_units_sd,ta_est_err_units_mean,p_est_within_half_unit,"
               "closed_loop,cl_correction_units_mean,cl_residual_units_mean,"
               "cl_evm_mean,cl_evm_snr_db_mean,cl_recovered_fraction,"
               "cl_evm_plus_mean,cl_evm_minus_mean\n");

  // ---------------- the sweep ----------------
  std::vector<cf_t> tx(slot_size), stream, rxbuf(slot_size);
  const unsigned    nrep = 3;  // three back-to-back identical slots; demodulate the middle one
  std::vector<cf_t> eq_syms, row(rg_size);
  std::vector<float> eq_nvars;
  noop_notifier notif;

  for (int ta = opt.ta_min; ta <= opt.ta_max; ++ta) {
    const long long delta = std::llround(ta * ta_unit_samples);
    std::vector<double> evms;
    double est_snr_acc = 0.0, ta_est_acc = 0.0;
    std::vector<double> ta_est_ns_all;       // per-trial DM-RS time-alignment readings
    std::vector<double> cl_evms;             // per-trial EVM after the closed-loop correction
    std::vector<double> cl_evms_plus, cl_evms_minus;  // both correction signs, kept separately
    double cl_corr_acc = 0.0, cl_resid_acc = 0.0;
    unsigned cl_recovered = 0;

    for (unsigned t = 0; t < opt.trials; ++t) {
      fill_tx_grid();
      modulator->modulate(tx, tx_grid->get_reader(), 0, 0);

      // continuous transmission: nrep identical slots
      stream.assign(slot_size * nrep + chan_len + 1, 0.0F);
      std::vector<cf_t> conc(slot_size * nrep);
      for (unsigned r = 0; r < nrep; ++r) std::copy(tx.begin(), tx.end(), conc.begin() + r * slot_size);

      // draw tap gains
      std::vector<cf_t> h(taps.size());
      for (size_t n = 0; n < taps.size(); ++n)
        h[n] = cf_t{gauss(rng), gauss(rng)} * static_cast<float>(std::sqrt(taps[n].p_lin));
      // relay: an ADDED delayed copy of the same (already faded) transmit signal.
      std::vector<cf_t> hr;
      if (opt.relay) {
        hr.resize(taps.size());
        for (size_t n = 0; n < taps.size(); ++n)
          hr[n] = cf_t{gauss(rng), gauss(rng)} *
                  static_cast<float>(std::sqrt(taps[n].p_lin) * relay_gain);
      }

      // convolve
      for (size_t i = 0; i < conc.size(); ++i) {
        const cf_t s = conc[i];
        if (s == cf_t{0.0F, 0.0F}) continue;
        for (size_t n = 0; n < taps.size(); ++n) {
          size_t j = i + taps[n].d;
          if (j < stream.size()) stream[j] += s * h[n];
          if (opt.relay) {
            size_t jr = j + relay_delay_samples;
            if (jr < stream.size()) stream[jr] += s * hr[n];
          }
        }
      }

      // AWGN at the requested per-RE SNR
      const double snr_lin = std::pow(10.0, opt.snr_db / 10.0);
      const double n0      = sig_power_per_re / (snr_lin * noise_gain_per_re);
      std::normal_distribution<float> ng(0.0F, static_cast<float>(std::sqrt(n0 / 2.0)));
      for (cf_t& s : stream) s += cf_t{ng(rng), ng(rng)};

      // Read the middle slot, shifted by delta.  delta > 0 => read later => signal early.
      // `measure(extra)` performs one complete receive pass with the window moved by `extra`
      // samples on top of delta, and returns the post-equalisation EVM, the DM-RS
      // time-alignment reading and the estimated SNR.  It is a lambda so that the closed loop
      // can run the identical receive chain twice on the SAME received samples.
      struct pass_result {
        double evm;
        double ta_est_ns;
        double snr_db;
      };

      auto measure = [&](long long extra) -> pass_result {
        const long long start = static_cast<long long>(slot_size) + delta + extra;
        if (start < 0 || start + slot_size > static_cast<long long>(stream.size())) {
          return {std::nan(""), std::nan(""), std::nan("")};
        }
        std::copy(stream.begin() + start, stream.begin() + start + slot_size, rxbuf.begin());

        rx_grid->set_all_zero();
        demodulator->demodulate(rx_grid->get_writer(), rxbuf, 0, 0);

        // srsRAN's own DM-RS channel estimation
        channel_estimate::channel_estimate_dimensions dims;
        dims.nof_prb = opt.nof_prb; dims.nof_symbols = nsymb; dims.nof_rx_ports = 1;
        dims.nof_tx_layers = 1;
        channel_estimate est(dims);
        estimator->estimate(est, notif, rx_grid->get_reader(), ecfg);

        // srsRAN's own ZF equaliser, per data OFDM symbol
        span<const cbf16_t> ce_all = est.get_path_ch_estimate(0, 0);
        double err = 0.0, sigp = 0.0;
        eq_syms.resize(rg_size); eq_nvars.resize(rg_size);
        for (unsigned l : data_symbols) {
          rx_grid->get_reader().get(row, 0, l, 0);
          static_re_buffer<1, MAX_RB * NRE, cbf16_t> chsym;
          chsym.resize(1, rg_size);
          span<cbf16_t> dst = chsym.get_slice(0);
          for (unsigned k = 0; k < rg_size; ++k) dst[k] = row[k];
          modular_ch_est_list<1> cel(rg_size, 1, 1);
          cel.set_channel(ce_all.subspan(static_cast<size_t>(l) * rg_size, rg_size), 0, 0);
          const float nv = est.get_noise_variance(0);
          equalizer->equalize(eq_syms, eq_nvars, chsym, cel,
                              span<const float>(&nv, 1), 1.0F);
          for (unsigned k = 0; k < rg_size; ++k) {
            const cf_t d = eq_syms[k] - ref[l][k];
            err  += std::norm(d);
            sigp += std::norm(ref[l][k]);
          }
        }
        return {std::sqrt(err / sigp),
                est.get_time_alignment(0, 0).to_seconds() * 1e9,
                static_cast<double>(est.get_snr_dB(0))};
      };

      // ---- pass 1: the receiver's nominal window
      const pass_result p1 = measure(0);
      est_snr_acc += p1.snr_db;
      ta_est_acc  += p1.ta_est_ns;
      ta_est_ns_all.push_back(p1.ta_est_ns);
      evms.push_back(p1.evm);

      // ---- pass 2: the closed loop.  A Timing Advance Command conveys a whole number of TA
      // units (TS 38.213 clause 4.2), so the correction the receiver can actually ask for is
      // the DM-RS reading rounded to the nearest unit.
      //
      // srsRAN's reported time alignment turns out to carry the OPPOSITE sign from this
      // driver's `ta` convention (measured: at |ta| <= 4 the reading is -ta + 0.57 units), so
      // applying it with the wrong sign would DOUBLE the error rather than cancel it.  Rather
      // than depend on getting that convention right, both signs are applied and both results
      // reported; `cl_evm_mean` is the better of the two, i.e. the most generous possible
      // reading of what a re-tracking receiver could achieve.
      if (opt.closed_loop) {
        const double corr_units = std::round(p1.ta_est_ns / (ta_unit_s * 1e9));
        const pass_result pp = measure(+std::llround(corr_units * ta_unit_samples));
        const pass_result pm = measure(-std::llround(corr_units * ta_unit_samples));
        const double ep = std::isnan(pp.evm) ? 1e9 : pp.evm;
        const double em = std::isnan(pm.evm) ? 1e9 : pm.evm;
        const double best = std::min(ep, em);
        cl_evms_plus.push_back(ep);
        cl_evms_minus.push_back(em);
        cl_evms.push_back(best);
        // "recovered" = the corrected pass lands at an EVM a 1/2-rate QPSK link can carry.
        // -10 dB EVM (0.3162) is below every Leg-2 waterfall threshold, so it is a generous
        // criterion, again chosen against the attack.
        if (best <= 0.3162) {
          ++cl_recovered;
        }
        cl_corr_acc  += corr_units;
        cl_resid_acc += std::min(std::abs(static_cast<double>(ta) + corr_units),
                                 std::abs(static_cast<double>(ta) - corr_units));
      }
    }

    const double n    = evms.size();
    const double mean = std::accumulate(evms.begin(), evms.end(), 0.0) / n;
    double var = 0.0;
    for (double v : evms) var += (v - mean) * (v - mean);
    const double sd = std::sqrt(var / std::max(1.0, n - 1.0));
    std::vector<double> srt = evms;
    std::sort(srt.begin(), srt.end());
    const double p90 = srt[std::min<size_t>(srt.size() - 1, static_cast<size_t>(0.90 * srt.size()))];

    // DM-RS time-alignment estimator statistics, in TA units, against the known true error.
    const double unit_ns   = ta_unit_s * 1e9;
    double est_mean_ns = 0.0;
    for (double v : ta_est_ns_all) est_mean_ns += v;
    est_mean_ns /= std::max<size_t>(1, ta_est_ns_all.size());
    double est_var_ns = 0.0;
    for (double v : ta_est_ns_all) est_var_ns += (v - est_mean_ns) * (v - est_mean_ns);
    const double est_sd_ns = std::sqrt(est_var_ns / std::max(1.0, double(ta_est_ns_all.size()) - 1.0));
    unsigned within_half = 0;
    for (double v : ta_est_ns_all) {
      if (std::abs(v / unit_ns - static_cast<double>(ta)) <= 0.5) ++within_half;
    }

    // Closed-loop statistics.
    double cl_mean = std::nan(""), cl_snr = std::nan("");
    double cl_rec = std::nan(""), cl_corr = std::nan(""), cl_resid = std::nan("");
    double cl_plus = std::nan(""), cl_minus = std::nan("");
    if (opt.closed_loop && !cl_evms.empty()) {
      double acc = 0.0;
      size_t cnt = 0;
      for (double v : cl_evms) {
        if (!std::isnan(v)) { acc += v; ++cnt; }
      }
      if (cnt > 0) {
        cl_mean = acc / double(cnt);
        cl_snr  = -20.0 * std::log10(std::max(1e-9, cl_mean));
      }
      auto avg = [](const std::vector<double>& v) {
        double a = 0.0;
        size_t c = 0;
        for (double x : v) {
          if (!std::isnan(x) && x < 1e8) { a += x; ++c; }
        }
        return (c > 0) ? a / double(c) : std::nan("");
      };
      cl_plus  = avg(cl_evms_plus);
      cl_minus = avg(cl_evms_minus);
      cl_rec   = double(cl_recovered) / double(cl_evms.size());
      cl_corr  = cl_corr_acc / double(cl_evms.size());
      cl_resid = cl_resid_acc / double(cl_evms.size());
    }

    std::fprintf(out,
                 "%u,%u,%u,%u,%s,%.1f,%s,%.2f,%.2f,%s,%s,%d,%.2f,%.2f,%d,%s,%.3f,%u,"
                 "%.6f,%.6f,%.6f,%.3f,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,"
                 "%d,%.4f,%.4f,%.6f,%.3f,%.4f,%.6f,%.6f\n",
                 opt.mu, scs_to_khz(scs), opt.dft_size, opt.nof_prb,
                 opt.awgn_only ? "AWGN-flat" : prof.name, opt.ds_ns, opt.mod.c_str(), opt.snr_db,
                 opt.win_offset, opt.fd_strategy.c_str(), opt.td_strategy.c_str(),
                 opt.relay ? 1 : 0, opt.relay_delay_ta, opt.relay_power_db,
                 ta, (ta > 0 ? "EARLY_arrival_attack_dir" : (ta < 0 ? "LATE_arrival" : "aligned")),
                 ta * ta_unit_s * 1e9, opt.trials, mean, sd, p90,
                 -20.0 * std::log10(std::max(1e-9, mean)), est_snr_acc / opt.trials,
                 ta_est_acc / opt.trials,
                 est_sd_ns, est_mean_ns / unit_ns, est_sd_ns / unit_ns,
                 est_mean_ns / unit_ns - static_cast<double>(ta),
                 double(within_half) / double(std::max<size_t>(1, ta_est_ns_all.size())),
                 opt.closed_loop ? 1 : 0, cl_corr, cl_resid, cl_mean, cl_snr, cl_rec,
                 cl_plus, cl_minus);
    std::fflush(out);
  }
  if (out != stdout) std::fclose(out);
  return 0;
}
