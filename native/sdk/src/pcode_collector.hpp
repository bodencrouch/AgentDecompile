// Emitters that collect raw p-code and assembly into flat arrays.
#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "gnsdk/gnsdk.h"
#include "upstream.hpp"

namespace gnsdk {

// Backing store behind a gnsdk_pcode_out; owned via out->_owner.
struct PcodeStore {
  std::vector<gnsdk_pcode_op> ops;
  std::vector<gnsdk_varnode> varnodes;
  std::vector<gnsdk_pcode_instr> instrs;
  std::vector<std::string> space_names;
  std::vector<const char*> space_ptrs;  // rebuilt by finalize()
  std::map<const ghidra::AddrSpace*, std::uint32_t> space_index;

  std::uint32_t space_id(const ghidra::AddrSpace* spc);
  void finalize();  // fills space_ptrs; call before handing out pointers
};

class PcodeCollector final : public ghidra::PcodeEmit {
 public:
  explicit PcodeCollector(PcodeStore& store) : store_(store) {}
  void dump(const ghidra::Address& addr, ghidra::OpCode opc, ghidra::VarnodeData* outvar,
            ghidra::VarnodeData* vars, ghidra::int4 isize) override;

 private:
  PcodeStore& store_;
};

// One "0x<addr>\t<mnemonic>\t<operands>\n" line per instruction.
class AsmCollector final : public ghidra::AssemblyEmit {
 public:
  explicit AsmCollector(std::string& out) : out_(out) {}
  void dump(const ghidra::Address& addr, const std::string& mnem, const std::string& body) override;

 private:
  std::string& out_;
};

}  // namespace gnsdk
