// Export per-function inventory rows as JSONL for AgentDecompile source-parity pipelines.
// @category Export
// @keybinding
// @menupath
// @toolbar

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.mem.MemoryBlock;

import com.google.gson.Gson;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.LinkedHashMap;
import java.util.Map;

public class ExportFunctionInventory extends GhidraScript {

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: ExportFunctionInventory.java <output.jsonl>");
        }

        File out = new File(args[0]);
        File parent = out.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        Gson gson = new Gson();
        Listing listing = currentProgram.getListing();
        Memory memory = currentProgram.getMemory();
        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        int count = 0;

        try (BufferedWriter writer = new BufferedWriter(new FileWriter(out))) {
            while (functions.hasNext()) {
                monitor.checkCancelled();
                Function function = functions.next();
                Address entry = function.getEntryPoint();
                long entryOffset = entry.getOffset();
                String entryHex = String.format("%08x", entryOffset);
                AddressSetView body = function.getBody();
                int bodyBytes = (int) body.getNumAddresses();

                MemoryBlock block = memory.getBlock(entry);
                String section = block != null ? block.getName() : "";

                int instructionCount = 0;
                InstructionIterator instructions = listing.getInstructions(body, true);
                while (instructions.hasNext()) {
                    monitor.checkCancelled();
                    instructions.next();
                    instructionCount++;
                }

                StringBuilder hex = new StringBuilder(bodyBytes * 2);
                for (Address addr : body.getAddresses(true)) {
                    monitor.checkCancelled();
                    try {
                        byte value = memory.getByte(addr);
                        hex.append(String.format("%02x", value & 0xff));
                    } catch (MemoryAccessException e) {
                        // Skip unreadable bytes inside the function body.
                    }
                }

                Map<String, Object> row = new LinkedHashMap<>();
                row.put("name", function.getName());
                row.put("entry", entryHex);
                row.put("entryOffset", entryOffset);
                row.put("section", section);
                row.put("bodyBytes", bodyBytes);
                java.util.List<Map<String, Object>> bodyRanges = new java.util.ArrayList<>();
                ghidra.program.model.address.AddressRangeIterator ranges = body.getAddressRanges();
                while (ranges.hasNext()) {
                    ghidra.program.model.address.AddressRange range = ranges.next();
                    Map<String, Object> extent = new LinkedHashMap<>();
                    extent.put("start", String.format("%08x", range.getMinAddress().getOffset()));
                    extent.put("endInclusive", String.format("%08x", range.getMaxAddress().getOffset()));
                    bodyRanges.add(extent);
                }
                row.put("bodyRanges", bodyRanges);
                row.put("instructionCount", instructionCount);
                row.put("bytes", hex.toString());

                writer.write(gson.toJson(row));
                writer.newLine();
                count++;
            }
        }

        monitor.checkCancelled();
        println("ExportFunctionInventory COMPLETE " + count + " functions to " + out.getAbsolutePath());
    }
}
