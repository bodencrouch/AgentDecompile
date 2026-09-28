#include "pcode_collector.hpp"

#include <cstdio>

namespace gnsdk {

std::uint32_t PcodeStore::space_id(const ghidra::AddrSpace* spc) {
  auto it = space_index.find(spc);
  if (it != space_index.end()) return it->second;
  auto id = static_cast<std::uint32_t>(space_names.size());
  space_names.push_back(spc != nullptr ? spc->getName() : std::string("<null>"));
  space_index.emplace(spc, id);
  return id;
}

void PcodeStore::finalize() {
  space_ptrs.clear();
  space_ptrs.reserve(space_names.size());
  for (const auto& n : space_names) space_ptrs.push_back(n.c_str());
}

void PcodeCollector::dump(const ghidra::Address& addr, ghidra::OpCode opc, ghidra::VarnodeData* outvar,
                          ghidra::VarnodeData* vars, ghidra::int4 isize) {
  gnsdk_pcode_op op{};
  op.opcode = static_cast<std::uint32_t>(opc);
  op.instr_addr = static_cast<std::uint64_t>(addr.getOffset());
  op.output_index = -1;
  if (outvar != nullptr) {
    op.output_index = static_cast<std::int32_t>(store_.varnodes.size());
    store_.varnodes.push_back(gnsdk_varnode{store_.space_id(outvar->space), outvar->size,
                                            static_cast<std::uint64_t>(outvar->offset)});
  }
  op.first_input = static_cast<std::uint32_t>(store_.varnodes.size());
  op.num_inputs = isize > 0 ? static_cast<std::uint32_t>(isize) : 0u;
  for (ghidra::int4 i = 0; i < isize; ++i) {
    store_.varnodes.push_back(gnsdk_varnode{store_.space_id(vars[i].space), vars[i].size,
                                            static_cast<std::uint64_t>(vars[i].offset)});
  }
  store_.ops.push_back(op);
}

void AsmCollector::dump(const ghidra::Address& addr, const std::string& mnem, const std::string& body) {
  char buf[32];
  std::snprintf(buf, sizeof buf, "0x%llx", static_cast<unsigned long long>(addr.getOffset()));
  out_ += buf;
  out_ += '\t';
  out_ += mnem;
  out_ += '\t';
  out_ += body;
  out_ += '\n';
}

}  // namespace gnsdk
