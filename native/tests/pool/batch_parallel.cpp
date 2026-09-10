#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <sys/wait.h>
#include <unistd.h>

#include "worker/json_min.hpp"
#include "wtest.hpp"

namespace
{

struct Run
{
    int code = -1;
    std::chrono::milliseconds elapsed{0};
};

std::filesystem::path make_temp_dir()
{
    const char *base = std::getenv("TMPDIR");
    std::filesystem::path root = (base != nullptr && *base != '\0') ? base : "/tmp";
    const auto dir = root / ("gnsdk-batch-parallel-" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    return dir;
}

int exit_status(int system_code)
{
    if (system_code < 0)
        return system_code;
    if (WIFEXITED(system_code))
        return WEXITSTATUS(system_code);
    return -1;
}

Run run_batch(const std::filesystem::path &dir, int workers, const char *batch_path,
              const std::string &input_name, const std::string &output_name)
{
    const auto output = dir / output_name;
    const std::string command =
        std::string("\"") + batch_path + "\"" + " --sleigh-home /nonexistent" + " --input \"" +
        (dir / input_name).string() + "\"" + " --output \"" + output.string() + "\"" +
        " --timeout 5" + " --workers " + std::to_string(workers) + " --tmpdir \"" + dir.string() +
        "\"" + " >/dev/null 2>\"" + (dir / ("stderr-" + output_name + ".log")).string() + "\"";
    const auto begin = std::chrono::steady_clock::now();
    const int code = std::system(command.c_str());
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - begin);
    return {code, elapsed};
}

Run run_batch(const std::filesystem::path &dir, int workers)
{
    return run_batch(dir, workers, GNSDK_BATCH_FAKE_PATH, "jobs.jsonl",
                     "out-" + std::to_string(workers) + ".jsonl");
}

std::vector<std::string> ids(const std::filesystem::path &path)
{
    std::ifstream input(path);
    std::vector<std::string> out;
    std::string line;
    while (std::getline(input, line))
    {
        gnsdk::json::Value value;
        if (!gnsdk::json::parse(line, value))
            throw std::runtime_error("invalid result JSONL");
        std::string id;
        if (!value.get_string("id", id))
            throw std::runtime_error("missing result id");
        out.push_back(std::move(id));
    }
    return out;
}

} // namespace

int main()
{
    const auto dir = make_temp_dir();
    {
        std::ofstream jobs(dir / "jobs.jsonl");
        jobs
            << R"({"id":"first","snapshot":"/fake/one.xml","ops":[{"op":"decompile","addr":"0x1"}]})"
            << '\n';
        jobs
            << R"({"id":"second","snapshot":"/fake/two.xml","ops":[{"op":"decompile","addr":"0x2"}]})"
            << '\n';
    }
    {
        std::ofstream jobs(dir / "bad-jobs.jsonl");
        jobs << R"({"id":"bad","snapshot":"/fake/one.xml","ops":[]})" << '\n';
    }

    const auto one = run_batch(dir, 1);
    const auto two = run_batch(dir, 2);
    REQUIRE(exit_status(one.code) == 0);
    REQUIRE(exit_status(two.code) == 0);
    REQUIRE(ids(dir / "out-1.jsonl") == std::vector<std::string>({"first", "second"}));
    REQUIRE(ids(dir / "out-2.jsonl") == std::vector<std::string>({"first", "second"}));
    REQUIRE(two.elapsed < one.elapsed);
    REQUIRE(
        exit_status(
            run_batch(dir, 1, GNSDK_BATCH_FAKE_PATH, "bad-jobs.jsonl", "bad-output.jsonl").code) ==
        2);
    REQUIRE(exit_status(run_batch(dir, 1, GNSDK_BATCH_MISSING_WORKER_PATH, "jobs.jsonl",
                                  "missing-worker-output.jsonl")
                            .code) == 1);

    std::error_code ignored;
    std::filesystem::remove_all(dir, ignored);
    return wtest::exit_code();
}
