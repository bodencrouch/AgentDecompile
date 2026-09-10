#include <atomic>
#include <chrono>
#include <stdexcept>
#include <thread>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

namespace
{
gnsdk::pool::Config base_config()
{
    gnsdk::pool::Config config;
    config.worker = GNSDK_FAKE_WORKER_PATH;
    config.sleigh_home = "/nonexistent";
    config.worker_args = {"--misbehave", "honor-cancel"};
    config.cancel_grace = std::chrono::milliseconds(20);
    config.term_grace = std::chrono::milliseconds(20);
    return config;
}

proto::Message slow_decompile(gnsdk::pool::Supervisor &pool, std::uint64_t id,
                              std::chrono::milliseconds worker_delay)
{
    const std::string payload = R"({"addr":"0x401000","tokens":false,"deadline_ms":)" +
                                std::to_string(worker_delay.count()) + "}";
    return pool.request(proto::Kind::Decompile, payload, id, std::chrono::seconds(2));
}

std::size_t slow_payload_size(std::chrono::milliseconds worker_delay)
{
    const std::string payload = R"({"addr":"0x401000","tokens":false,"deadline_ms":)" +
                                std::to_string(worker_delay.count()) + "}";
    return payload.size();
}
} // namespace

int main()
{
    {
        auto config = base_config();
        config.workers = 1;
        config.max_queue = 1;

        gnsdk::pool::Supervisor pool(std::move(config));
        pool.start();

        std::atomic_bool first_started{false};
        bool first_ok = false;
        std::thread first(
            [&]()
            {
                first_started = true;
                const auto reply = slow_decompile(pool, 1, std::chrono::milliseconds(250));
                first_ok = reply.kind == proto::to_u16(proto::Kind::Result);
            });

        while (!first_started)
            std::this_thread::yield();
        std::this_thread::sleep_for(std::chrono::milliseconds(50));

        bool rejected = false;
        try
        {
            (void)slow_decompile(pool, 2, std::chrono::milliseconds(1));
        }
        catch (const std::runtime_error &)
        {
            rejected = true;
        }
        first.join();
        REQUIRE(first_ok);
        REQUIRE(rejected);
        REQUIRE(pool.live_workers() == 1);
        pool.stop();
        REQUIRE(pool.live_workers() == 0);
    }

    {
        auto config = base_config();
        config.workers = 1;
        config.max_queue = 2;
        config.max_queue_bytes = slow_payload_size(std::chrono::milliseconds(250)) + 8;

        gnsdk::pool::Supervisor pool(std::move(config));
        pool.start();

        bool first_ok = false;
        std::thread first(
            [&]()
            {
                const auto reply = slow_decompile(pool, 21, std::chrono::milliseconds(250));
                first_ok = reply.kind == proto::to_u16(proto::Kind::Result);
            });
        std::this_thread::sleep_for(std::chrono::milliseconds(50));

        bool rejected = false;
        try
        {
            (void)slow_decompile(pool, 22, std::chrono::milliseconds(1));
        }
        catch (const std::runtime_error &)
        {
            rejected = true;
        }
        first.join();

        REQUIRE(first_ok);
        REQUIRE(rejected);
        REQUIRE(pool.live_workers() == 1);
        pool.stop();
        REQUIRE(pool.live_workers() == 0);
    }

    {
        auto config = base_config();
        config.workers = 2;
        config.max_queue = 2;

        gnsdk::pool::Supervisor pool(std::move(config));
        pool.start();

        bool first_ok = false;
        bool second_ok = false;
        const auto begin = std::chrono::steady_clock::now();
        std::thread first(
            [&]()
            {
                const auto reply = slow_decompile(pool, 11, std::chrono::milliseconds(250));
                first_ok = reply.kind == proto::to_u16(proto::Kind::Result);
            });
        std::thread second(
            [&]()
            {
                const auto reply = slow_decompile(pool, 12, std::chrono::milliseconds(250));
                second_ok = reply.kind == proto::to_u16(proto::Kind::Result);
            });
        first.join();
        second.join();
        const auto elapsed = std::chrono::steady_clock::now() - begin;

        REQUIRE(first_ok);
        REQUIRE(second_ok);
        REQUIRE(elapsed < std::chrono::milliseconds(450));
        REQUIRE(pool.live_workers() == 2);
        pool.stop();
        REQUIRE(pool.live_workers() == 0);
    }

    return wtest::exit_code();
}
