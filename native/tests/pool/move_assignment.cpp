#include <cerrno>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>
#include <vector>

#include <sys/wait.h>
#include <unistd.h>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace
{
std::vector<pid_t> child_pids()
{
    std::ifstream input("/proc/self/task/" + std::to_string(::getpid()) + "/children");
    std::vector<pid_t> children;
    pid_t pid = -1;
    while (input >> pid)
        children.push_back(pid);
    return children;
}

gnsdk::pool::Config config(std::size_t workers)
{
    gnsdk::pool::Config value;
    value.worker = GNSDK_FAKE_WORKER_PATH;
    value.sleigh_home = "/nonexistent";
    value.workers = workers;
    value.cancel_grace = std::chrono::milliseconds(20);
    value.term_grace = std::chrono::milliseconds(20);
    return value;
}
} // namespace

int main()
{
    if (!std::filesystem::exists(
            "/proc/self/task/" + std::to_string(::getpid()) + "/children"))
        return 0;
    gnsdk::pool::Supervisor destination(config(2));
    destination.start();
    const auto old_children = child_pids();
    REQUIRE(old_children.size() == 2);

    gnsdk::pool::Supervisor replacement(config(1));
    replacement.start();
    REQUIRE(child_pids().size() == 3);

    destination = std::move(replacement);
    REQUIRE(destination.live_workers() == 1);
    REQUIRE(replacement.live_workers() == 0);
    for (const pid_t pid : old_children)
    {
        errno = 0;
        REQUIRE(::waitpid(pid, nullptr, WNOHANG) == -1);
        REQUIRE(errno == ECHILD);
    }

    destination.stop();
    REQUIRE(child_pids().empty());
    return wtest::exit_code();
}
