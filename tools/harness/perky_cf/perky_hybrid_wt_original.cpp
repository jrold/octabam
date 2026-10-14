// Exact WT control/render gate against the user's original PĒRKONS v1.2.1.
// Compile with the existing PerkyBits reference runtime and production CF
// units. Wrapper captures extend past the WT object: V1 object+0x12c is the
// global target array at 0x20000694. Compare every owned byte from +0x1c
// through +0x12b, and independently prove the +0x12c..0x14f sentinel is neither
// read nor written.
#include "FirmwareImage.h"
#include "PerkonsM7.h"
#include "PerkonsVoices.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
extern "C" {
#include "cf_perky4.h"
}
namespace fs = std::filesystem;
using Raw =
    std::array<uint8_t, 4>; // TUNE, DECAY, PARAM1, PARAM2 (firmware order).
constexpr size_t OWNED_END = 0x12c, OWNED_FIRST = 0x1c;
static std::vector<uint8_t> read(const fs::path &p) {
  std::ifstream f(p, std::ios::binary);
  if (!f)
    throw std::runtime_error("read " + p.string());
  return {std::istreambuf_iterator<char>(f), {}};
}
static uint32_t target(unsigned x) { return x == 127 ? 4095 : x << 5; }
struct Counters {
  uint64_t cases = 0, state = 0, pcm = 0, failures = 0;
};
static std::map<std::string, Counters> counts;
struct WavetableSelectionCoverage {
  unsigned observations = 0;
  std::set<uint32_t> addresses;
  std::set<unsigned> mixes;
  std::map<std::string, std::vector<unsigned>> boundaries;
};
static std::map<std::pair<unsigned, unsigned>, WavetableSelectionCoverage>
    wt_selections;

static std::vector<std::string> failures;
static std::string section, label;
static uint64_t release_calls = 0;
static void fail(const std::string &m) {
  ++counts[section].failures;
  if (failures.size() < 24)
    failures.push_back(section + " " + label + " " + m);
}
static void state_equal(const uint8_t *a, const uint8_t *b,
                        size_t first = OWNED_FIRST, size_t end = OWNED_END) {
  ++counts[section].state;
  for (size_t i = first; i < end; i++)
    if (a[i] != b[i]) {
      fail("state offset=" + std::to_string(i) +
           " got=" + std::to_string(a[i]) + " want=" + std::to_string(b[i]));
      return;
    }
}
static void pcm_equal(const int16_t *a, const int16_t *b, size_t n) {
  counts[section].pcm += n;
  for (size_t i = 0; i < n; i++)
    if (a[i] != b[i]) {
      fail("PCM sample=" + std::to_string(i) + " got=" + std::to_string(a[i]) +
           " want=" + std::to_string(b[i]));
      return;
    }
}
struct Assets {
  pk4_assets a{};
  std::array<std::vector<uint8_t>, 13> b;
  explicit Assets(const fs::path &p) {
    const char *names[] = {"pitch",   "chromatic", "envelope1", "envelope2",
                           "m1",      "interp_a",  "interp_b",  "wt_base",
                           "wt_bank", "w0",        "w1",        "w2",
                           "w3"};
    for (unsigned i = 0; i < 13; i++)
      b[i] = read(p / (std::string(names[i]) + ".bin"));
    a.pitch = b[0].data();
    a.chromatic = b[1].data();
    a.envelope1 = b[2].data();
    a.envelope2 = b[3].data();
    a.m1_wave = b[4].data();
    a.m1_wave_address = 0x080310e0u;
    a.res_interp_a = b[5].data();
    a.res_interp_b = b[6].data();
    a.wt_base = b[7].data();
    a.wt_bank = b[8].data();
    for (unsigned i = 0; i < 4; i++)
      a.waves[i] = {0x080222a0u + i * 0x200, b[9 + i].data()};
  }
};
struct Original {
  PerkonsM7 cpu;
  PerkonsVoices v;
  PerkonsVoices::Slot slot;
  uint32_t object;
  std::string err;
  bool valid = false;
  Raw last{};
  unsigned last_mode = 0;
  Original(const FirmwareImage &fw, unsigned family)
      : v(cpu), slot(family == 2 ? PerkonsVoices::Slot::voice1
                                 : PerkonsVoices::Slot::voice2),
        object(family == 2 ? 0x20000568u : 0x200009f0u) {
    must(cpu.load(fw, err));
    must(v.initialise(fw, err));
    v.setNativeDspEnabledForTesting(false);
  }
  void must(bool b) {
    if (!b)
      throw std::runtime_error(err);
  }
  void prepare(const Raw &r, unsigned mode, bool trig) {
    bool dirty = !valid || r != last || mode != last_mode;
    if (dirty) {
      // These are the original wrapper operations used by the historical
      // capture: two passes under old targets, mode selection, 16 passes under
      // new targets.
      must(v.setAlgorithm(slot, 1, err));
      must(v.setMode(slot, std::array<uint8_t, 3>{1, 0, 2}[mode], err));
      std::array<uint16_t, 4> t{};
      for (unsigned i = 0; i < 4; i++)
        t[i] = (uint16_t)target(r[i]);
      must(v.setSoundParameters(slot, t, err));
      last = r;
      last_mode = mode;
      valid = true;
    }
    if (trig)
      must(v.trigger(slot, err));
  }
  std::array<uint8_t, PK_CF_WT_STATE_BYTES> state() {
    std::array<uint8_t, PK_CF_WT_STATE_BYTES> s{};
    must(cpu.readMemory(object, s.data(), s.size(), err));
    return s;
  }
  std::vector<int16_t> render(unsigned n) {
    std::vector<int16_t> p(n);
    must(v.renderInto(slot, p.data(), n, err));
    return p;
  }
  void release() {
    ++release_calls;
    must(v.release(slot, err));
  }
  void family_away() {
    must(v.setAlgorithm(slot, 0, err));
    must(v.setMode(slot, 1, err));
    must(v.setSoundParameters(slot, {2048, 2048, 2048, 2048}, err));
    must(v.trigger(slot, err));
    auto other = render(16);
    (void)other;
  }
  void resonant_away(unsigned mode) {
    auto rs = PerkonsVoices::Slot::voice3;
    must(v.setAlgorithm(rs, 0, err));
    must(v.setMode(rs, std::array<uint8_t, 3>{1, 0, 2}[mode], err));
    must(v.setSoundParameters(rs, {2048, 2048, 2048, 2048}, err));
    must(v.trigger(rs, err));
    std::array<int16_t, 16> other{};
    must(v.renderInto(rs, other.data(), 16, err));
  }
};
static void prepare(pk4_engine &e, unsigned tr, const Raw &r, unsigned mode,
                    bool trig) {
  if (!pk4_prepare_event(&e, tr, r[1], r[0], r[2], r[3], mode,
                         PK4_ALGO_WAVETABLE, 255, trig ? 45 : 63, trig))
    throw std::runtime_error("CF prepare rejected");
}
static void compare(pk4_engine &e, unsigned tr, Original &o) {
  auto want = o.state();
  state_equal(e.tracks[tr].wt, want.data());
}
static void render(pk4_engine &e, unsigned tr, Original &o, unsigned n) {
  for (unsigned base = 0; base < n; base += 16) {
    unsigned block = std::min(16u, n - base);
    std::array<int16_t, 16> got{};
    if (!pk4_render(&e, tr, got.data(), block))
      throw std::runtime_error("CF render rejected");
    auto want = o.render(block);
    pcm_equal(got.data(), want.data(), block);
    compare(e, tr, o);
  }
}
static void fixture_corpus(const FirmwareImage &fw, const Assets &a,
                           const fs::path &fixtures) {
  section = "pinned_corpus";
  for (unsigned family : {2, 5})
    for (unsigned tr : {0, 1})
      for (unsigned mode = 0; mode < 3; mode++)
        for (unsigned corner = 0; corner < 3; corner++) {
          auto engine = std::make_unique<pk4_engine>();
          pk4_init(engine.get(), &a.a);
          Original original(fw, family);
          Raw raw{};
          raw.fill(std::array<uint8_t, 3>{0, 64, 127}[corner]);
          const size_t offset = family == 2 ? 0x2e8 : 0x31c;
          auto path = fixtures / ("engine-" + std::to_string(family) +
                                  "-mode-" + std::to_string(mode + 1) +
                                  "-corner-" + std::to_string(corner));
          label = "family=" + std::to_string(family) +
                  " tr=" + std::to_string(tr) +
                  " mode=" + std::to_string(mode) +
                  " corner=" + std::to_string(corner);
          ++counts[section].cases;
          for (const char *stage :
               {"pre-trigger", "before", "after", "continuation-after",
                "retrigger-before", "retrigger-after"}) {
            std::string name = stage;
            if (name == "pre-trigger") {
              prepare(*engine, tr, raw, mode, false);
              original.prepare(raw, mode, false);
            } else if (name == "before" || name == "retrigger-before") {
              prepare(*engine, tr, raw, mode, true);
              original.prepare(raw, mode, true);
            } else {
              const char *pcmfile = name == "after" ? "arm-pcm.bin"
                                    : name == "continuation-after"
                                        ? "arm-pcm-continuation.bin"
                                        : "arm-pcm-retrigger.bin";
              std::array<int16_t, 256> got{};
              for (unsigned b = 0; b < 16; b++)
                if (!pk4_render(engine.get(), tr, got.data() + b * 16, 16))
                  throw std::runtime_error("render");
              auto live = original.render(256);
              auto want = read(path / pcmfile);
              pcm_equal(got.data(),
                        reinterpret_cast<const int16_t *>(want.data()), 256);
              pcm_equal(live.data(),
                        reinterpret_cast<const int16_t *>(want.data()), 256);
            }
            auto want = read(path / ("wrapper-window-" + name + ".bin"));
            auto live = original.state();
            state_equal(engine->tracks[tr].wt, want.data() + offset);
            state_equal(live.data(), want.data() + offset);
          }
        }
  std::cout << "pinned corpus completed\n" << std::flush;
}
// Observe original ARM state inside the existing public-control grid.  Require
// all sixteen tables in each mode, both mix endpoints, and both sides of every
// table-pair boundary for each logical instance and preparation path.
static void observe_wt_selection(unsigned family, unsigned tr, unsigned mode,
                                 unsigned raw, bool direct, unsigned &previous,
                                 const uint8_t *state) {
  auto &coverage = wt_selections[{family, mode}];
  ++coverage.observations;
  auto word = [&](size_t offset) {
    return uint32_t(state[offset]) | (uint32_t(state[offset + 1]) << 8) |
           (uint32_t(state[offset + 2]) << 16) |
           (uint32_t(state[offset + 3]) << 24);
  };
  uint32_t a = word(0x104), b = word(0x10c);
  const uint32_t base = 0x080327ccu;
  for (uint32_t address : {a, b}) {
    coverage.addresses.insert(address);
    if (address < base || address >= base + 48u * 4096u ||
        (address - base) % 4096u)
      fail("original WT table pointer outside aligned bank");
  }
  coverage.mixes.insert(unsigned(state[0x114]) | (unsigned(state[0x115]) << 8));
  auto &boundaries = coverage.boundaries["logical_" + std::to_string(tr) +
                                         (direct ? "_direct" : "_settled")];
  if (raw && a != previous)
    boundaries.push_back(raw);
  previous = a;
}
static void validate_wt_selection_coverage() {
  if (wt_selections.size() != 6)
    fail("WT selection coverage missing a family/mode");
  const std::vector<unsigned> boundaries = {9,  18, 26, 35, 43,  52,  60,
                                            69, 77, 86, 94, 103, 111, 120};
  for (unsigned family : {2, 5})
    for (unsigned mode = 0; mode < 3; mode++) {
      const auto found = wt_selections.find({family, mode});
      if (found == wt_selections.end()) {
        fail("missing WT family/mode selections");
        continue;
      }
      const auto &coverage = found->second;
      std::set<uint32_t> expected;
      for (unsigned i = mode * 16; i < (mode + 1) * 16; i++)
        expected.insert(0x080327ccu + i * 4096u);
      if (coverage.observations != 512 || coverage.addresses != expected ||
          !coverage.mixes.count(0) || !coverage.mixes.count(255) ||
          *coverage.mixes.rbegin() > 255 || coverage.boundaries.size() != 4)
        fail("incomplete WT table or crossfade endpoint coverage");
      for (unsigned tr : {0, 1})
        for (bool direct : {false, true}) {
          auto path = "logical_" + std::to_string(tr) +
                      (direct ? "_direct" : "_settled");
          auto observed = coverage.boundaries.find(path);
          if (observed == coverage.boundaries.end() ||
              observed->second != boundaries)
            fail("missing WT raw table boundary for " + path);
        }
    }
}
static void boundary_grid(const FirmwareImage &fw, const Assets &a) {
  section = "boundary_grid";
  for (unsigned family : {2, 5})
    for (unsigned tr : {0, 1})
      for (unsigned mode = 0; mode < 3; mode++) {
        std::array<unsigned, 2> previous_address{};
        for (unsigned ctl = 0; ctl < 4; ctl++)
          for (unsigned value = 0; value < 128; value++)
            for (bool direct : {false, true}) {
              Raw raw{64, 64, 64, 64};
              raw[ctl] = (uint8_t)value;
              Original original(fw, family);
              auto engine = std::make_unique<pk4_engine>();
              pk4_init(engine.get(), &a.a);
              label = "family=" + std::to_string(family) +
                      " tr=" + std::to_string(tr) +
                      " mode=" + std::to_string(mode) +
                      " ctl=" + std::to_string(ctl) +
                      " raw=" + std::to_string(value) +
                      " direct=" + std::to_string(direct);
              ++counts[section].cases;
              if (!direct) {
                prepare(*engine, tr, raw, mode, false);
                original.prepare(raw, mode, false);
                compare(*engine, tr, original);
              }
              prepare(*engine, tr, raw, mode, true);
              original.prepare(raw, mode, true);
              if (ctl == 2) {
                auto state = original.state();
                observe_wt_selection(family, tr, mode, value, direct,
                                     previous_address[direct ? 1 : 0],
                                     state.data());
              }
              compare(*engine, tr, original);
              render(*engine, tr, original, 32);
            }
        std::cout << "boundary family " << family << " logical " << tr
                  << " mode " << mode << " completed\n"
                  << std::flush;
      }
  validate_wt_selection_coverage();
}
static void paired_trajectories(const FirmwareImage &fw, const Assets &a,
                                bool legacy = false) {
  section = "paired_trajectories";
  auto together = std::make_unique<pk4_engine>();
  pk4_init(together.get(), &a.a);
  std::array<std::unique_ptr<pk4_engine>, 2> alone;
  std::array<std::unique_ptr<Original>, 2> original;
  std::array<Raw, 2> last{};
  std::array<unsigned, 2> mode{};
  for (unsigned tr = 0; tr < 2; tr++) {
    alone[tr] = std::make_unique<pk4_engine>();
    pk4_init(alone[tr].get(), &a.a);
    original[tr] = std::make_unique<Original>(fw, tr == 0 ? 2 : 5);
  }
  for (unsigned event = 0; event < 192; event++) {
    for (unsigned j = 0; j < 2; j++) {
      unsigned tr = (j + event) % 2;
      mode[tr] = (event + tr) % 3;
      Raw raw{(uint8_t)((event * 17 + tr * 61) % 128),
              (uint8_t)((event * 29 + tr * 31) % 128),
              (uint8_t)((event * 43 + tr * 11) % 128),
              (uint8_t)((event * 67 + tr * 37) % 128)};
      bool trig = (event % 4) != 1;
      last[tr] = raw;
      label = "event=" + std::to_string(event) + " tr=" + std::to_string(tr);
      ++counts[section].cases;
      auto untouched = together->tracks[1 - tr];
      prepare(*together, tr, raw, mode[tr], trig);
      prepare(*alone[tr], tr, raw, mode[tr], trig);
      original[tr]->prepare(raw, mode[tr], trig);
      state_equal(reinterpret_cast<const uint8_t *>(&together->tracks[1 - tr]),
                  reinterpret_cast<const uint8_t *>(&untouched), 0,
                  sizeof(untouched));
      compare(*together, tr, *original[tr]);
      state_equal(together->tracks[tr].wt, alone[tr]->tracks[tr].wt, 0,
                  PK_CF_WT_STATE_BYTES);
      if (event % 13 == 0) {
        auto before = original[tr]->state();
        original[tr]->release();
        auto after = original[tr]->state();
        state_equal(before.data(), after.data(), 0, PK_CF_WT_STATE_BYTES);
      }
      unsigned samples = event % 31 == 0 ? 4096 : 64;
      for (unsigned k = 0; k < samples; k += 16) {
        std::array<int16_t, 16> x{}, y{};
        if (!pk4_render(together.get(), tr, x.data(), 16) ||
            !pk4_render(alone[tr].get(), tr, y.data(), 16))
          throw std::runtime_error("paired render");
        auto z = original[tr]->render(16);
        pcm_equal(x.data(), y.data(), 16);
        pcm_equal(x.data(), z.data(), 16);
        compare(*together, tr, *original[tr]);
        state_equal(together->tracks[tr].wt, alone[tr]->tracks[tr].wt, 0,
                    PK_CF_WT_STATE_BYTES);
      }
    }
  }
  std::cout << "paired dirty trajectories, modes, retriggers, releases and "
               "tails completed\n"
            << std::flush;
  // Preserve WT state while another family runs, then return with new controls.
  section = legacy ? "legacy_fold_roundtrip" : "hybrid_resonant_roundtrip";
  for (unsigned tr = 0; tr < 2; tr++)
    for (unsigned event = 0; event < 12; event++) {
      label = "tr=" + std::to_string(tr) + " event=" + std::to_string(event);
      ++counts[section].cases;
      auto before = together->tracks[tr].wt;
      std::array<uint8_t, PK_CF_WT_STATE_BYTES> saved{};
      std::memcpy(saved.data(), before, saved.size());
      if (!pk4_prepare_event(together.get(), tr, 64, 64, 64, 64, event % 3,
                             legacy ? PK4_ALGO_FOLD1 : PK4_ALGO_RESONANT, 255,
                             45, 1))
        throw std::runtime_error("away prepare");
      std::array<int16_t, 16> junk{};
      if (!pk4_render(together.get(), tr, junk.data(), 16))
        throw std::runtime_error("away render");
      state_equal(together->tracks[tr].wt, saved.data(), 0, saved.size());
      if (legacy)
        original[tr]->family_away();
      else
        original[tr]->resonant_away(event % 3);
      Raw raw{(uint8_t)(event * 7), (uint8_t)(127 - event * 3),
              (uint8_t)(event * 11), (uint8_t)(event * 5)};
      prepare(*together, tr, raw, event % 3, true);
      original[tr]->prepare(raw, event % 3, true);
      compare(*together, tr, *original[tr]);
      render(*together, tr, *original[tr], 64);
    }
  std::cout << "family roundtrips completed\n" << std::flush;
}
// Host-only hybrid profile adapter. Historical public enums stay intact.
// Distinct V1 and V2 profiles own separate WT objects for each logical
// instance. The four existing test slots provide storage; this does not
// prescribe the future firmware allocation or change historical voice-silo
// routing.
enum class HybridProfile : unsigned { WavetableV1, WavetableV2, Resonant };
struct NarrowProfileAdapter {
  pk4_engine engine{};
  std::array<HybridProfile, 2> active{};
  explicit NarrowProfileAdapter(const pk4_assets *assets) {
    pk4_init(&engine, assets);
  }
  static unsigned slot(unsigned logical, HybridProfile profile) {
    return logical + (profile == HybridProfile::WavetableV2 ? 2u : 0u);
  }
  void event(unsigned logical, HybridProfile profile, const Raw &raw,
             unsigned mode, bool trig) {
    unsigned tr = slot(logical, profile);
    unsigned algo = profile == HybridProfile::Resonant ? PK4_ALGO_RESONANT
                                                       : PK4_ALGO_WAVETABLE;
    if (!pk4_prepare_event(&engine, tr, raw[1], raw[0], raw[2], raw[3], mode,
                           algo, 255, trig ? 45 : 63, trig))
      throw std::runtime_error("profile prepare");
    active[logical] = profile;
  }
  std::vector<int16_t> render(unsigned logical, unsigned n) {
    std::vector<int16_t> pcm(n);
    unsigned tr = slot(logical, active[logical]);
    for (unsigned b = 0; b < n; b += 16)
      if (!pk4_render(&engine, tr, pcm.data() + b, std::min(16u, n - b)))
        throw std::runtime_error("profile render");
    return pcm;
  }
};
struct OriginalRes {
  PerkonsM7 cpu;
  PerkonsVoices v;
  std::string err;
  bool valid = false;
  Raw last{};
  unsigned mode = 2;
  unsigned last_mode = 2;
  explicit OriginalRes(const FirmwareImage &fw, unsigned m = 2)
      : v(cpu), mode(m) {
    must(cpu.load(fw, err));
    must(v.initialise(fw, err));
    v.setNativeDspEnabledForTesting(false);
  }
  void must(bool b) {
    if (!b)
      throw std::runtime_error(err);
  }
  void prepare(const Raw &raw, bool trig) {
    auto slot = PerkonsVoices::Slot::voice3;
    if (!valid || raw != last || mode != last_mode) {
      must(v.setAlgorithm(slot, 0, err));
      must(v.setMode(slot, std::array<uint8_t, 3>{1, 0, 2}[mode], err));
      std::array<uint16_t, 4> targets{};
      for (unsigned i = 0; i < 4; i++)
        targets[i] = (uint16_t)target(raw[i]);
      must(v.setSoundParameters(slot, targets, err));
      last = raw;
      last_mode = mode;
      valid = true;
    }
    if (trig)
      must(v.trigger(slot, err));
  }
  size_t size() const {
    return std::array<size_t, 3>{PK_CF_RES_SNARE_STATE_BYTES, 0x180u,
                                 PK_CF_NT_STATE_BYTES}[mode];
  }
  size_t offset() const {
    return std::array<size_t, 3>{0x2734, 0x39e8, 0x3b68}[mode];
  }
  std::vector<uint8_t> state() {
    std::vector<uint8_t> s(size());
    must(cpu.readMemory(0x20003930u + offset(), s.data(), s.size(), err));
    return s;
  }
  std::array<uint32_t, 2> rng() {
    uint32_t manager = 0, address = 0;
    std::array<uint32_t, 2> r{1, 0};
    must(cpu.readMemory(0x20000024u, &manager, 4, err));
    must(cpu.readMemory(manager + 0x30u, &address, 4, err));
    if (address)
      must(cpu.readMemory(address + 0x10u, r.data(), 8, err));
    return r;
  }
  std::vector<int16_t> render(unsigned n) {
    std::vector<int16_t> p(n);
    must(v.renderInto(PerkonsVoices::Slot::voice3, p.data(), n, err));
    return p;
  }
  void release() {
    ++release_calls;
    must(v.release(PerkonsVoices::Slot::voice3, err));
  }
};
static void prepare_res_live(pk4_engine &e, unsigned tr, const Raw &raw,
                             bool trig, unsigned mode = 2) {
  if (!pk4_prepare_event(&e, tr, raw[1], raw[0], raw[2], raw[3], mode,
                         PK4_ALGO_RESONANT, 255, trig ? 45 : 63, trig))
    throw std::runtime_error("Res M3 prepare");
}
static void compare_res_live(pk4_engine &e, unsigned tr, OriginalRes &o,
                             bool rng = true) {
  auto state = o.state();
  const uint8_t *cf = o.mode == 0   ? e.tracks[tr].res_snare
                      : o.mode == 1 ? e.tracks[tr].res_bass
                                    : e.tracks[tr].res_nt;
  state_equal(cf, state.data(), 0x1c, o.size());
  if (rng) {
    auto expected = o.rng();
    ++counts[section].state;
    if (e.tracks[tr].rng_low != expected[0] ||
        e.tracks[tr].rng_high != expected[1])
      fail("RNG mismatch");
  }
}
static void render_res_live(pk4_engine &e, unsigned tr, OriginalRes &o,
                            unsigned n) {
  for (unsigned b = 0; b < n; b += 16) {
    unsigned count = std::min(16u, n - b);
    std::array<int16_t, 16> got{};
    if (!pk4_render(&e, tr, got.data(), count))
      throw std::runtime_error("Res M3 render");
    auto want = o.render(count);
    pcm_equal(got.data(), want.data(), count);
    compare_res_live(e, tr, o);
  }
}
static void resonant_original(const FirmwareImage &fw, const Assets &a,
                              const fs::path &fixtures) {
  for (unsigned mode = 0; mode < 3; mode++) {
    const std::string prefix = "resonant_mode_" + std::to_string(mode + 1);
    section = prefix + "_corpus";
    for (unsigned tr : {0, 1})
      for (unsigned corner = 0; corner < 3; corner++) {
        auto e = std::make_unique<pk4_engine>();
        pk4_init(e.get(), &a.a);
        OriginalRes o(fw, mode);
        Raw raw{};
        raw.fill(std::array<uint8_t, 3>{0, 64, 127}[corner]);
        auto path = fixtures / ("engine-7-mode-" + std::to_string(mode + 1) +
                                "-corner-" + std::to_string(corner));
        label =
            "tr=" + std::to_string(tr) + " corner=" + std::to_string(corner);
        ++counts[section].cases;
        for (const char *stage :
             {"pre-trigger", "before", "after", "continuation-after",
              "retrigger-before", "retrigger-after"}) {
          std::string st = stage;
          if (st == "pre-trigger") {
            prepare_res_live(*e, tr, raw, false, mode);
            o.prepare(raw, false);
          } else if (st == "before" || st == "retrigger-before") {
            prepare_res_live(*e, tr, raw, true, mode);
            o.prepare(raw, true);
          } else {
            std::array<int16_t, 256> got{};
            for (unsigned b = 0; b < 16; b++)
              if (!pk4_render(e.get(), tr, got.data() + 16 * b, 16))
                throw std::runtime_error("Res capture render");
            auto live = o.render(256);
            const char *name = st == "after" ? "arm-pcm.bin"
                               : st == "continuation-after"
                                   ? "arm-pcm-continuation.bin"
                                   : "arm-pcm-retrigger.bin";
            auto want = read(path / name);
            pcm_equal(got.data(),
                      reinterpret_cast<const int16_t *>(want.data()), 256);
            pcm_equal(live.data(),
                      reinterpret_cast<const int16_t *>(want.data()), 256);
            compare_res_live(*e, tr, o);
          }
          auto want = read(path / ("wrapper-window-" + st + ".bin"));
          auto live = o.state();
          const uint8_t *cf = mode == 0   ? e->tracks[tr].res_snare
                              : mode == 1 ? e->tracks[tr].res_bass
                                          : e->tracks[tr].res_nt;
          state_equal(cf, want.data() + o.offset(), 0x1c, o.size());
          state_equal(live.data(), want.data() + o.offset(), 0x1c, o.size());
        }
      }
    std::cout << "Resonant mode " << mode + 1
              << " original capture corpus completed\n"
              << std::flush;
    section = prefix + "_grid";
    for (unsigned tr : {0, 1})
      for (unsigned control = 0; control < 4; control++) {
        for (unsigned value = 0; value < 128; value++)
          for (bool direct : {false, true}) {
            Raw raw{64, 64, 64, 64};
            raw[control] = (uint8_t)value;
            OriginalRes o(fw, mode);
            auto e = std::make_unique<pk4_engine>();
            pk4_init(e.get(), &a.a);
            label = "tr=" + std::to_string(tr) +
                    " control=" + std::to_string(control) +
                    " raw=" + std::to_string(value) +
                    " direct=" + std::to_string(direct);
            ++counts[section].cases;
            if (!direct) {
              prepare_res_live(*e, tr, raw, false, mode);
              o.prepare(raw, false);
              compare_res_live(*e, tr, o, false);
            }
            prepare_res_live(*e, tr, raw, true, mode);
            o.prepare(raw, true);
            compare_res_live(*e, tr, o, false);
            render_res_live(*e, tr, o, 32);
          }
        std::cout << "Resonant mode " << mode + 1 << " logical " << tr
                  << " control " << control << " grid completed\n"
                  << std::flush;
      }
    section = prefix + "_trajectories";
    auto combined = std::make_unique<pk4_engine>();
    pk4_init(combined.get(), &a.a);
    std::array<std::unique_ptr<pk4_engine>, 2> isolated;
    std::array<std::unique_ptr<OriginalRes>, 2> original;
    for (unsigned tr = 0; tr < 2; tr++) {
      isolated[tr] = std::make_unique<pk4_engine>();
      pk4_init(isolated[tr].get(), &a.a);
      original[tr] = std::make_unique<OriginalRes>(fw, mode);
    }
    for (unsigned event = 0; event < 192; event++)
      for (unsigned order = 0; order < 2; order++) {
        unsigned tr = (event + order) % 2;
        Raw raw{(uint8_t)((event * 19 + tr * 17) % 128),
                (uint8_t)((event * 47 + tr * 71) % 128),
                (uint8_t)((event * 61 + tr * 29) % 128),
                (uint8_t)((event * 31 + tr * 53) % 128)};
        bool trig = event % 4 != 1;
        label = "event=" + std::to_string(event) + " tr=" + std::to_string(tr);
        ++counts[section].cases;
        auto untouched = combined->tracks[1 - tr];
        prepare_res_live(*combined, tr, raw, trig, mode);
        prepare_res_live(*isolated[tr], tr, raw, trig, mode);
        original[tr]->prepare(raw, trig);
        compare_res_live(*combined, tr, *original[tr], false);
        state_equal(
            reinterpret_cast<const uint8_t *>(&combined->tracks[1 - tr]),
            reinterpret_cast<const uint8_t *>(&untouched), 0,
            sizeof(untouched));
        if (event % 13 == 0) {
          auto before = original[tr]->state();
          original[tr]->release();
          auto after = original[tr]->state();
          state_equal(before.data(), after.data(), 0, original[tr]->size());
        }
        unsigned n = event % 31 == 0 ? 4096 : 64;
        for (unsigned b = 0; b < n; b += 16) {
          std::array<int16_t, 16> x{}, y{};
          if (!pk4_render(combined.get(), tr, x.data(), 16) ||
              !pk4_render(isolated[tr].get(), tr, y.data(), 16))
            throw std::runtime_error("Res paired render");
          auto z = original[tr]->render(16);
          pcm_equal(x.data(), y.data(), 16);
          pcm_equal(x.data(), z.data(), 16);
          compare_res_live(*combined, tr, *original[tr]);
          state_equal(
              reinterpret_cast<const uint8_t *>(&combined->tracks[tr]),
              reinterpret_cast<const uint8_t *>(&isolated[tr]->tracks[tr]), 0,
              sizeof(pk4_track));
        }
      }
    std::cout << "Resonant mode " << mode + 1
              << " two-instance original PCM/state/RNG trajectories "
                 "completed\n"
              << std::flush;
  }
}

static void resonant_transitions(const FirmwareImage &fw, const Assets &a) {
  section = "resonant_mode_transitions";
  auto e = std::make_unique<pk4_engine>();
  pk4_init(e.get(), &a.a);
  std::array<std::unique_ptr<OriginalRes>, 2> refs;
  for (unsigned tr = 0; tr < 2; tr++)
    refs[tr] = std::make_unique<OriginalRes>(fw, 0);
  for (unsigned event = 0; event < 96; event++)
    for (unsigned tr = 0; tr < 2; tr++) {
      unsigned mode = (event + tr) % 3;
      auto &o = *refs[tr];
      o.mode = mode;
      Raw raw{(uint8_t)((event * 7 + tr * 17) % 128),
              (uint8_t)((event * 11 + tr * 71) % 128),
              (uint8_t)((event * 61 + tr * 29) % 128),
              (uint8_t)((event * 31 + tr * 53) % 128)};
      bool trig = event % 5 != 2;
      label = "event=" + std::to_string(event) + " tr=" + std::to_string(tr) +
              " mode=" + std::to_string(mode);
      ++counts[section].cases;
      prepare_res_live(*e, tr, raw, trig, mode);
      o.prepare(raw, trig);
      compare_res_live(*e, tr, o, false);
      render_res_live(*e, tr, o, event % 23 == 0 ? 2048 : 64);
    }
  std::cout << "Resonant original mode transitions completed\n" << std::flush;
}
static void profile_retention(const FirmwareImage &fw, const Assets &a) {
  section = "hybrid_profile_retention";
  auto combined = std::make_unique<NarrowProfileAdapter>(&a.a);
  std::array<std::unique_ptr<NarrowProfileAdapter>, 2> isolated;
  std::array<std::array<std::unique_ptr<Original>, 2>, 2> reference;
  std::array<std::unique_ptr<OriginalRes>, 2> resonant;
  for (unsigned logical = 0; logical < 2; logical++) {
    isolated[logical] = std::make_unique<NarrowProfileAdapter>(&a.a);
    resonant[logical] = std::make_unique<OriginalRes>(fw, 0);
    for (unsigned profile = 0; profile < 2; profile++)
      reference[logical][profile] =
          std::make_unique<Original>(fw, profile == 0 ? 2 : 5);
  }
  for (unsigned event = 0; event < 144; event++)
    for (unsigned order = 0; order < 2; order++) {
      unsigned logical = (order + event) % 2, which = (event + logical) % 3,
               mode = (event / 3 + logical) % 3;
      HybridProfile profile = (HybridProfile)which;
      Raw raw{(uint8_t)((event * 31 + logical * 17) % 128),
              (uint8_t)((event * 11 + logical * 71) % 128),
              (uint8_t)((event * 67 + logical * 29) % 128),
              (uint8_t)((event * 43 + logical * 53) % 128)};
      bool trig = event % 4 != 1;
      label = "event=" + std::to_string(event) +
              " logical=" + std::to_string(logical) +
              " profile=" + std::to_string(which);
      ++counts[section].cases;
      auto other0 = combined->engine.tracks[1 - logical],
           other1 = combined->engine.tracks[3 - logical];
      combined->event(logical, profile, raw, mode, trig);
      isolated[logical]->event(logical, profile, raw, mode, trig);
      if (which < 2)
        reference[logical][which]->prepare(raw, mode, trig);
      else {
        resonant[logical]->mode = mode;
        resonant[logical]->prepare(raw, trig);
      }
      unsigned tr = NarrowProfileAdapter::slot(logical, profile),
               n = event % 19 == 0 ? 2048 : 64;
      auto got = combined->render(logical, n),
           alone = isolated[logical]->render(logical, n);
      pcm_equal(got.data(), alone.data(), n);
      state_equal(reinterpret_cast<const uint8_t *>(
                      &combined->engine.tracks[1 - logical]),
                  reinterpret_cast<const uint8_t *>(&other0), 0,
                  sizeof(other0));
      state_equal(reinterpret_cast<const uint8_t *>(
                      &combined->engine.tracks[3 - logical]),
                  reinterpret_cast<const uint8_t *>(&other1), 0,
                  sizeof(other1));
      state_equal(
          reinterpret_cast<const uint8_t *>(&combined->engine.tracks[tr]),
          reinterpret_cast<const uint8_t *>(
              &isolated[logical]->engine.tracks[tr]),
          0, sizeof(pk4_track));
      if (which < 2) {
        auto want = reference[logical][which]->render(n);
        pcm_equal(got.data(), want.data(), n);
        auto state = reference[logical][which]->state();
        state_equal(combined->engine.tracks[tr].wt, state.data());
      } else {
        auto want = resonant[logical]->render(n);
        pcm_equal(got.data(), want.data(), n);
      }
      if (resonant[logical]->valid)
        compare_res_live(combined->engine, logical, *resonant[logical]);
      // Both WT identities retain their own original object's continuing state,
      // including while the same logical instance renders the Resonant family.
      for (unsigned p = 0; p < 2; p++)
        if (reference[logical][p]->valid) {
          auto state = reference[logical][p]->state();
          state_equal(
              combined->engine
                  .tracks[NarrowProfileAdapter::slot(logical, (HybridProfile)p)]
                  .wt,
              state.data());
        }
    }
  std::cout
      << "separate V1/V2 profiles and Resonant family retention completed\n"
      << std::flush;
}

static void isolated_constructor(const FirmwareImage &fw,
                                 const fs::path &fixtures) {
  section = "isolated_constructor";
  const uint32_t obj = 0x20010000, params = 0x20011000;
  for (unsigned family : {2, 5})
    for (unsigned mode = 0; mode < 3; mode++)
      for (unsigned corner = 0; corner < 3; corner++) {
        PerkonsM7 cpu;
        std::string err;
        auto must = [&](bool b) {
          if (!b)
            throw std::runtime_error(err);
        };
        must(cpu.load(fw, err));
        std::array<uint8_t, 0x150> s{};
        for (unsigned i = 0x12c; i < s.size(); i++)
          s[i] = (uint8_t)(i ^ 0x5a);
        s[6] = 255;
        s[7] = 63;
        s[8] = 0xf0;
        s[9] = 15;
        must(cpu.writeMemory(obj, s.data(), s.size(), err));
        for (unsigned i = 0; i < 4; i++)
          must(cpu.write32(obj + 0xc + 4 * i, params + 4 * i, err));
        auto call = [&](uint32_t fn) {
          auto r = cpu.callThumb(fn, {obj, 0, 0, 0});
          if (!r.ok)
            throw std::runtime_error(r.message);
        };
        call(0x080270e0);
        must(cpu.write8(obj + 5, std::array<uint8_t, 3>{1, 0, 2}[mode], err));
        unsigned value = std::array<unsigned, 3>{0, 2048, 4095}[corner];
        for (unsigned i = 0; i < 4; i++)
          must(cpu.write32(params + i * 4, value, err));
        for (unsigned i = 0; i < 16; i++)
          call(0x08027160);
        auto path = fixtures / ("engine-" + std::to_string(family) + "-mode-" +
                                std::to_string(mode + 1) + "-corner-" +
                                std::to_string(corner));
        size_t off = family == 2 ? 0x2e8 : 0x31c;
        label = "family=" + std::to_string(family) +
                " mode=" + std::to_string(mode) +
                " corner=" + std::to_string(corner);
        ++counts[section].cases;
        for (const char *stage :
             {"pre-trigger", "before", "after", "continuation-after",
              "retrigger-before", "retrigger-after"}) {
          std::string st = stage;
          if (st == "before" || st == "retrigger-before") {
            must(cpu.write8(obj + 7, 45, err));
            call(0x0802714c);
            call(0x08027160);
          }
          const char *pcfile =
              st == "after"                ? "arm-pcm.bin"
              : st == "continuation-after" ? "arm-pcm-continuation.bin"
              : st == "retrigger-after"    ? "arm-pcm-retrigger.bin"
                                           : nullptr;
          if (pcfile) {
            auto r = cpu.renderInt16Block(obj, 0x0802700c, 256);
            if (!r.ok)
              throw std::runtime_error(r.message);
            auto want = read(path / pcfile);
            pcm_equal(r.samples.data(),
                      reinterpret_cast<const int16_t *>(want.data()), 256);
          }
          must(cpu.readMemory(obj, s.data(), s.size(), err));
          auto want = read(path / ("wrapper-window-" + st + ".bin"));
          state_equal(s.data(), want.data() + off);
          ++counts[section].state;
          for (unsigned i = 0x12c; i < s.size(); i++)
            if (s[i] != (uint8_t)(i ^ 0x5a)) {
              fail("sentinel tail mutated at " + std::to_string(i));
              break;
            }
        }
      }
  std::cout << "isolated original constructor and sentinel tail completed\n"
            << std::flush;
}
// Two isolated original objects differ only in every byte beyond owned_end.
// Exact state and PCM equality proves those tested paths neither read nor write
// it.
static void isolated_boundary(const FirmwareImage &fw) {
  section = "isolated_boundary";
  PerkonsM7 cpu;
  std::string err;
  auto must = [&](bool b) {
    if (!b)
      throw std::runtime_error(err);
  };
  must(cpu.load(fw, err));
  const std::array<uint32_t, 2> objects = {0x20010000, 0x20012000};
  const uint32_t params = 0x20011000;
  for (unsigned mode = 0; mode < 3; mode++)
    for (unsigned control = 0; control < 4; control++)
      for (unsigned value = 0; value < 128; value++) {
        label = "mode=" + std::to_string(mode) +
                " control=" + std::to_string(control) +
                " raw=" + std::to_string(value);
        ++counts[section].cases;
        std::array<std::array<uint8_t, 0x150>, 2> states{};
        for (unsigned j = 0; j < 2; j++) {
          auto &s = states[j];
          s[6] = 255;
          s[7] = 63;
          s[8] = 0xf0;
          s[9] = 15;
          for (size_t i = OWNED_END; i < s.size(); i++)
            s[i] = (uint8_t)(i ^ (j ? 0xa5 : 0x5a));
          must(cpu.writeMemory(objects[j], s.data(), s.size(), err));
          for (unsigned i = 0; i < 4; i++)
            must(cpu.write32(objects[j] + 0xc + 4 * i, params + 4 * i, err));
        }
        auto call = [&](unsigned j, uint32_t fn) {
          auto r = cpu.callThumb(fn, {objects[j], 0, 0, 0});
          if (!r.ok)
            throw std::runtime_error(r.message);
        };
        for (unsigned i = 0; i < 4; i++)
          must(cpu.write32(params + 4 * i, 0, err));
        for (unsigned j = 0; j < 2; j++) {
          call(j, 0x080270e0);
          call(j, 0x08027160);
          must(cpu.write8(objects[j] + 5, std::array<uint8_t, 3>{1, 0, 2}[mode],
                          err));
          call(j, 0x08027160);
        }
        Raw raw{64, 64, 64, 64};
        raw[control] = (uint8_t)value;
        for (unsigned i = 0; i < 4; i++)
          must(cpu.write32(params + 4 * i, target(raw[i]), err));
        auto compare_pair = [&]() {
          for (unsigned j = 0; j < 2; j++) {
            must(cpu.readMemory(objects[j], states[j].data(), states[j].size(),
                                err));
            ++counts[section].state;
            for (size_t i = OWNED_END; i < states[j].size(); i++)
              if (states[j][i] != (uint8_t)(i ^ (j ? 0xa5 : 0x5a))) {
                fail("sentinel write offset=" + std::to_string(i));
                break;
              }
          }
          state_equal(states[0].data(), states[1].data());
        };
        for (unsigned j = 0; j < 2; j++)
          for (unsigned pass = 0; pass < 16; pass++)
            call(j, 0x08027160);
        compare_pair();
        for (unsigned j = 0; j < 2; j++) {
          must(cpu.write8(objects[j] + 7, 45, err));
          call(j, 0x0802714c);
          call(j, 0x08027160);
        }
        compare_pair();
        for (unsigned block = 0; block < 16; block++) {
          auto x = cpu.renderInt16Block(objects[0], 0x0802700c, 16);
          auto y = cpu.renderInt16Block(objects[1], 0x0802700c, 16);
          if (!x.ok || !y.ok)
            throw std::runtime_error("isolated boundary render");
          pcm_equal(x.samples.data(), y.samples.data(), 16);
          compare_pair();
        }
      }
  std::cout << "isolated original owned-boundary all128 controls completed\n"
            << std::flush;
}
static void long_tail_release(const FirmwareImage &fw, const Assets &a) {
  section = "wavetable_long_tail_release";
  for (unsigned family : {2, 5})
    for (unsigned tr : {0, 1})
      for (unsigned mode = 0; mode < 3; mode++) {
        ++counts[section].cases;
        label = "family=" + std::to_string(family) +
                " tr=" + std::to_string(tr) + " mode=" + std::to_string(mode);
        Original o(fw, family);
        auto e = std::make_unique<pk4_engine>();
        pk4_init(e.get(), &a.a);
        Raw raw{64, 64, (uint8_t)(mode * 63), (uint8_t)(127 - mode * 63)};
        prepare(*e, tr, raw, mode, true);
        o.prepare(raw, mode, true);
        render(*e, tr, o, 256);
        auto before = o.state();
        o.release();
        auto after = o.state();
        state_equal(before.data(), after.data(), 0, before.size());
        render(*e, tr, o, 65536);
        compare(*e, tr, o);
      }
  section = "resonant_long_tail_release";
  for (unsigned tr : {0, 1})
    for (unsigned mode = 0; mode < 3; mode++) {
      ++counts[section].cases;
      label = "tr=" + std::to_string(tr) + " mode=" + std::to_string(mode);
      OriginalRes o(fw, mode);
      auto e = std::make_unique<pk4_engine>();
      pk4_init(e.get(), &a.a);
      Raw raw{64, 64, (uint8_t)(mode * 63), (uint8_t)(127 - mode * 63)};
      prepare_res_live(*e, tr, raw, true, mode);
      o.prepare(raw, true);
      render_res_live(*e, tr, o, 256);
      auto before = o.state();
      o.release();
      auto after = o.state();
      state_equal(before.data(), after.data(), 0, before.size());
      render_res_live(*e, tr, o, 65536);
      compare_res_live(*e, tr, o);
    }
  std::cout << "65536sample postrelease original tails completed\n"
            << std::flush;
}
// Acceptance counts are fixed by the explicit loop bounds above.  A reduced
// diagnostic scope never emits an acceptance PASS.
static void validate_full_coverage() {
  const std::map<std::string, Counters> expected = {
      {"isolated_constructor", {18, 216, 13824, 0}},
      {"isolated_boundary", {1536, 82944, 393216, 0}},
      {"pinned_corpus", {36, 432, 55296, 0}},
      {"boundary_grid", {12288, 43008, 393216, 0}},
      {"paired_trajectories", {384, 11310, 162048, 0}},
      {"hybrid_resonant_roundtrip", {24, 144, 1536, 0}},
      {"hybrid_profile_retention", {288, 2199, 100352, 0}},
      {"resonant_mode_transitions", {192, 4208, 32128, 0}},
      {"wavetable_long_tail_release", {12, 49368, 789504, 0}},
      {"resonant_long_tail_release", {6, 49362, 394752, 0}},
      {"resonant_mode_1_corpus", {6, 108, 9216, 0}},
      {"resonant_mode_2_corpus", {6, 108, 9216, 0}},
      {"resonant_mode_3_corpus", {6, 108, 9216, 0}},
      {"resonant_mode_1_grid", {2048, 11264, 65536, 0}},
      {"resonant_mode_2_grid", {2048, 11264, 65536, 0}},
      {"resonant_mode_3_grid", {2048, 11264, 65536, 0}},
      {"resonant_mode_1_trajectories", {384, 15990, 162048, 0}},
      {"resonant_mode_2_trajectories", {384, 15990, 162048, 0}},
      {"resonant_mode_3_trajectories", {384, 15990, 162048, 0}}};
  if (counts.size() != expected.size() || release_calls != 138)
    throw std::runtime_error("full acceptance coverage missing");
  for (const auto &[name, want] : expected) {
    const auto it = counts.find(name);
    if (it == counts.end() || it->second.cases != want.cases ||
        it->second.state != want.state || it->second.pcm != want.pcm)
      throw std::runtime_error("coverage mismatch " + name);
  }
}
int main(int argc, char **argv) {
  if (argc < 5 || argc > 6) {
    std::cerr << "usage: perky_hybrid_wt_original firmware fixture-dir "
                 "asset-dir report.json "
                 "[all|corpus|grid|trajectory|profile|resonant|res-transitions|"
                 "wt-boundary|long-tail|legacy]\n";
    return 2;
  }
  try {
    FirmwareImage fw;
    std::string err;
    if (!fw.load(argv[1], err))
      throw std::runtime_error(err);
    Assets assets(argv[3]);
    std::string scope = argc == 6 ? argv[5] : "all";
    const std::vector<std::string> scopes = {
        "all",      "corpus",          "grid",        "trajectory", "profile",
        "resonant", "res-transitions", "wt-boundary", "long-tail",  "legacy"};
    if (std::find(scopes.begin(), scopes.end(), scope) == scopes.end())
      throw std::runtime_error("unknown diagnostic scope");
    if (scope == "all" || scope == "corpus") {
      isolated_constructor(fw, argv[2]);
      fixture_corpus(fw, assets, argv[2]);
    }
    if (scope == "all" || scope == "grid") {
      boundary_grid(fw, assets);
      isolated_boundary(fw);
    }
    if (scope == "all" || scope == "resonant") {
      resonant_original(fw, assets, argv[2]);
      resonant_transitions(fw, assets);
    }
    if (scope == "res-transitions")
      resonant_transitions(fw, assets);
    if (scope == "wt-boundary")
      isolated_boundary(fw);
    if (scope == "all" || scope == "long-tail")
      long_tail_release(fw, assets);
    if (scope == "all" || scope == "profile")
      profile_retention(fw, assets);
    if (scope == "all" || scope == "trajectory" || scope == "legacy")
      paired_trajectories(fw, assets, scope == "legacy");
    if (scope == "all")
      validate_full_coverage();
    uint64_t failed = 0;
    std::ofstream report(argv[4]);
    report << "{\n  \"sections\": {";
    bool comma = false;
    for (const auto &[name, c] : counts) {
      if (comma)
        report << ',';
      comma = true;
      failed += c.failures;
      report << "\n    \"" << name << "\": {\"cases\":" << c.cases
             << ",\"state_checks\":" << c.state << ",\"pcm_samples\":" << c.pcm
             << ",\"failures\":" << c.failures << '}';
      std::cout << name << ": cases=" << c.cases << " state=" << c.state
                << " PCM=" << c.pcm << " failures=" << c.failures << '\n';
    }
    report << "\n  },\n  \"wavetable_selection_coverage\": [";
    bool selection_comma = false;
    for (const auto &[key, coverage] : wt_selections) {
      if (selection_comma)
        report << ',';
      selection_comma = true;
      report << "\n    {\"original_family\":" << key.first
             << ",\"logical_mode\":" << key.second
             << ",\"observations\":" << coverage.observations
             << ",\"table_addresses\":[";
      bool separator = false;
      for (auto address : coverage.addresses) {
        if (separator)
          report << ',';
        separator = true;
        report << '"' << "0x" << std::hex << address << std::dec << '"';
      }
      report << "],\"mix_min\":" << *coverage.mixes.begin()
             << ",\"mix_max\":" << *coverage.mixes.rbegin()
             << ",\"raw_table_boundary_after\":{";
      separator = false;
      for (const auto &[path, observed] : coverage.boundaries) {
        if (separator)
          report << ',';
        separator = true;
        report << '"' << path << "\":[";
        for (size_t i = 0; i < observed.size(); i++) {
          if (i)
            report << ',';
          report << observed[i];
        }
        report << ']';
      }
      report << "}}";
    }
    report << "\n  ],\n  \"status\":\""
           << (failed           ? "FAIL"
               : scope == "all" ? "PASS"
                                : "DIAGNOSTIC_PASS")
           << "\",\n  \"scope\":\"" << scope
           << "\",\n  \"release_calls\":" << release_calls
           << ",\n  \"bounded_failures\":[";
    comma = false;
    for (const auto &m : failures) {
      if (comma)
        report << ',';
      comma = true;
      report << "\n    \"" << m << '"';
      std::cerr << m << '\n';
    }
    report << "\n  ]\n}\n";
    return failed ? 1 : 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 2;
  }
}
