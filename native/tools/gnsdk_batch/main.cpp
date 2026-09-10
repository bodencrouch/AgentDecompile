#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "gnsdk/pool.hpp"
#include "worker/json_min.hpp"

namespace json = gnsdk::json;
namespace proto = gnsdk::proto;

namespace {
struct Job { std::string id; std::string snapshot; std::string addr; };

bool parse_job(const json::Value& value, Job& job) {
  if (!value.is_object() || !value.get_string("id", job.id) || !value.get_string("snapshot", job.snapshot)) return false;
  const json::Value* ops = value.get_array("ops");
  if (ops == nullptr || ops->size() != 1 || !(*ops)[0].is_object()) return false;
  std::string op;
  return (*ops)[0].get_string("op", op) && op == "decompile" && (*ops)[0].get_string("addr", job.addr);
}

std::vector<Job> snapshot_jobs(const std::string& root) {
  std::ifstream input(root + "/manifest.json");
  std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  json::Value manifest;
  if (!input || !json::parse(text, manifest)) throw std::runtime_error("invalid snapshot manifest");
  const json::Value* functions = manifest.get_array("functions");
  if (functions == nullptr) throw std::runtime_error("snapshot has no functions array");
  std::vector<Job> jobs;
  for (const auto& entry : functions->items()) {
    std::string status, savefile, addr;
    if (!entry.get_string("status", status) || status != "ok" || !entry.get_string("savefile", savefile) || !entry.get_string("addr", addr)) continue;
    jobs.push_back({addr, root + "/" + savefile, "0x" + addr});
  }
  return jobs;
}

void write_record(std::ostream& output, const Job& job, const proto::Message& reply, std::uint64_t elapsed_ms) {
  json::Value record = json::Value::object(); record.set("id", job.id); record.set("seq", job.id); record.set("elapsed_ms", static_cast<unsigned long long>(elapsed_ms));
  json::Value payload;
  if (reply.kind == proto::to_u16(proto::Kind::Result) && json::parse(reply.json(), payload)) { record.set("status", "ok"); record.set("result", std::move(payload)); }
  else { record.set("status", "engine_failure"); record.set("error", std::string(reply.json())); }
  output << record.dump() << '\n';
}
}  // namespace

int main(int argc, char** argv) {
  std::string sleigh_home, input_path, snapshot_path, output_path;
  unsigned long timeout_s = 60;
  unsigned long workers = 1;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--version") { std::cout << "gnsdk-batch 0.1.0\n"; return 0; }
    if (i + 1 >= argc) return 2;
    const std::string value = argv[++i];
    if (arg == "--sleigh-home") sleigh_home = value;
    else if (arg == "--input") input_path = value;
    else if (arg == "--snapshot") snapshot_path = value;
    else if (arg == "--output") output_path = value;
    else if (arg == "--timeout") { try { timeout_s = std::stoul(value); } catch (...) { return 2; } }
    else if (arg == "--workers") { try { workers = std::stoul(value); } catch (...) { return 2; } }
    else return 2;
  }
  if (sleigh_home.empty() || output_path.empty() || (input_path.empty() == snapshot_path.empty()) ||
      timeout_s == 0 || workers == 0) return 2;
  try {
    std::vector<Job> jobs;
    if (!snapshot_path.empty()) jobs = snapshot_jobs(snapshot_path);
    else {
      std::ifstream input(input_path); std::string line;
      while (std::getline(input, line)) { if (line.empty()) continue; json::Value value; Job job; if (!json::parse(line, value) || !parse_job(value, job)) throw std::runtime_error("invalid JSONL job"); jobs.push_back(std::move(job)); }
      if (!input.eof()) throw std::runtime_error("cannot read input JSONL");
    }
    std::ofstream output(output_path); if (!output) throw std::runtime_error("cannot open output");
    // Snapshot restore owns a single process-global session. Keep it on one
    // worker until full affinity scheduling is implemented in Supervisor.
    gnsdk::pool::Config config; config.worker = GNSDK_WORKER_PATH; config.sleigh_home = sleigh_home;
    config.workers = snapshot_path.empty() ? static_cast<std::size_t>(workers) : 1;
    gnsdk::pool::Supervisor pool(std::move(config)); pool.start();
    std::uint64_t request = 1;
    for (const Job& job : jobs) {
      const auto begin = std::chrono::steady_clock::now();
      try {
        json::Value open = json::Value::object(); open.set("path", job.snapshot);
        const auto opened = pool.request(proto::Kind::OpenSnapshot, open.dump(), request++, std::chrono::seconds(timeout_s));
        if (opened.kind != proto::to_u16(proto::Kind::Result)) throw std::runtime_error("snapshot open failed");
        json::Value decompile = json::Value::object(); decompile.set("addr", job.addr); decompile.set("tokens", false); decompile.set("deadline_ms", static_cast<unsigned long long>(timeout_s * 1000)); decompile.set("printer", "c");
        const auto reply = pool.request(proto::Kind::Decompile, decompile.dump(), request++, std::chrono::seconds(timeout_s));
        write_record(output, job, reply, static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - begin).count()));
      } catch (const std::exception& exc) {
        json::Value record = json::Value::object(); record.set("id", job.id); record.set("seq", job.id); record.set("status", "engine_failure"); record.set("error", exc.what()); output << record.dump() << '\n';
      }
    }
    return 0;
  } catch (const std::exception& exc) { std::cerr << "gnsdk-batch: " << exc.what() << '\n'; return 2; }
}
