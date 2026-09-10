#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>

#include <fcntl.h>
#include <poll.h>
#include <sys/wait.h>
#include <unistd.h>

#include "worker/json_min.hpp"
#include "worker/protocol.hpp"
#include "spawn_util.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;
namespace json = gnsdk::json;

namespace {

struct Child {
  pid_t pid = -1;
  int in = -1;
  int out = -1;
  ~Child() {
    if (in >= 0) ::close(in);
    if (out >= 0) ::close(out);
    if (pid > 0) { ::kill(pid, SIGKILL); ::waitpid(pid, nullptr, 0); }
  }
};

Child spawn() {
  int to[2]; int from[2];
  REQUIRE(::pipe2(to, O_CLOEXEC) == 0);
  REQUIRE(::pipe2(from, O_CLOEXEC) == 0);
  const pid_t pid = ::fork();
  REQUIRE(pid >= 0);
  if (pid == 0) {
    ::dup2(to[0], 0); ::dup2(from[1], 1);
    ::close(to[0]); ::close(to[1]); ::close(from[0]); ::close(from[1]);
    const std::string expected_parent = std::to_string(::getppid());
    REQUIRE(::setenv("GNSDK_EXPECTED_PPID", expected_parent.c_str(), 1) == 0);
#if defined(GNSDK_ENABLE_TEST_HOOKS)
    ::execl(GNSDK_WORKER_PATH, GNSDK_WORKER_PATH, "--sleigh-home", GNSDK_SLEIGH_HOME,
            "--test-decompile-delay-ms", "200", static_cast<char*>(nullptr));
#else
    ::execl(GNSDK_WORKER_PATH, GNSDK_WORKER_PATH, "--sleigh-home", GNSDK_SLEIGH_HOME,
            static_cast<char*>(nullptr));
#endif
    _exit(127);
  }
  ::close(to[0]); ::close(from[1]);
  return {pid, to[1], from[0]};
}

void rejects_wrong_parent() {
  const pid_t pid = ::fork();
  REQUIRE(pid >= 0);
  if (pid == 0) {
    REQUIRE(::setenv("GNSDK_EXPECTED_PPID", "1", 1) == 0);
    ::execl(GNSDK_WORKER_PATH, GNSDK_WORKER_PATH, "--sleigh-home", GNSDK_SLEIGH_HOME,
            static_cast<char*>(nullptr));
    _exit(127);
  }
  int status = 0;
  REQUIRE(::waitpid(pid, &status, 0) == pid);
  REQUIRE(WIFEXITED(status));
  REQUIRE(WEXITSTATUS(status) == 5);
}

proto::Message receive(proto::FrameReader& reader, const Child& child, std::uint64_t id) {
  proto::MessageAssembler assembler(1 << 20);
  for (;;) {
    proto::Frame frame;
    pollfd pfd{child.out, POLLIN, 0};
    REQUIRE(::poll(&pfd, 1, 10000) > 0);
    REQUIRE(reader.read(child.out) == proto::ReadStatus::Progress);
    REQUIRE(reader.next(frame));
    const auto assembled = assembler.push(std::move(frame));
    REQUIRE(assembled == proto::AssembleStatus::NeedMore || assembled == proto::AssembleStatus::Complete);
    if (assembler.complete()) {
      auto message = assembler.take();
      REQUIRE(message.request_id == id);
      return message;
    }
  }
}

}  // namespace

int main() {
  rejects_wrong_parent();
  Child child = spawn();
  proto::FrameReader reader(proto::kPreHandshakeMaxFrame);
  proto::HelloInfo hello; hello.capabilities = {"test"}; hello.engine_source = "worker-e2e";
  proto::FrameWriter writer(child.in);
  REQUIRE(writer.write_json(proto::Kind::Hello, 0, proto::make_hello(hello)));
  proto::Frame ack;
  pollfd pfd{child.out, POLLIN, 0};
  REQUIRE(::poll(&pfd, 1, 10000) > 0);
  REQUIRE(reader.read(child.out) == proto::ReadStatus::Progress);
  REQUIRE(reader.next(ack));
  REQUIRE(ack.header.kind == proto::to_u16(proto::Kind::HelloAck));
  proto::HelloInfo remote; REQUIRE(proto::parse_hello(ack.payload_view(), remote));
  const auto negotiated = proto::negotiate(hello, remote); REQUIRE(negotiated.ok);
  reader.set_max_payload(negotiated.max_frame); writer.set_max_payload(negotiated.max_frame);

  const std::uint8_t code[] = {0x55, 0x48, 0x89, 0xe5, 0x31, 0xc0, 0x5d, 0xc3};
  REQUIRE(writer.write_json(proto::Kind::OpenRaw, 1,
      R"({"language":"x86:LE:64:default","base":"0x400000","length":8,"readonly":true})", proto::kFlagMore));
  REQUIRE(writer.write_raw(proto::Kind::OpenRaw, 1, code, sizeof(code)));
  auto opened = receive(reader, child, 1);
  REQUIRE(opened.kind == proto::to_u16(proto::Kind::Result));

  REQUIRE(writer.write_json(proto::Kind::Decompile, 2, R"({"addr":"0x400000","tokens":false,"deadline_ms":5000,"printer":"c"})"));
  auto result = receive(reader, child, 2);
  REQUIRE(result.kind == proto::to_u16(proto::Kind::Result));
  json::Value value; REQUIRE(json::parse(result.json(), value));
  std::string c; REQUIRE(value.get_string("c", c)); REQUIRE(!c.empty());

#if defined(GNSDK_ENABLE_TEST_HOOKS)
  // The test-only delay keeps this request active long enough to exercise the
  // real signal handler, not the protocol-level CANCEL fast path.
  REQUIRE(writer.write_json(proto::Kind::Decompile, 3, R"({"addr":"0x400000","tokens":false,"deadline_ms":5000,"printer":"c"})"));
  REQUIRE(::kill(child.pid, SIGUSR1) == 0);
  auto cancelled = receive(reader, child, 3);
  REQUIRE(cancelled.kind == proto::to_u16(proto::Kind::Error));

  REQUIRE(writer.write_json(proto::Kind::Decompile, 4, R"({"addr":"0x400000","tokens":false,"deadline_ms":5000,"printer":"c"})"));
  auto after_cancel = receive(reader, child, 4);
  REQUIRE(after_cancel.kind == proto::to_u16(proto::Kind::Result));
#endif

  REQUIRE(writer.write_empty(proto::Kind::Bye));
  ::close(child.in); child.in = -1;
  int status = 0; REQUIRE(::waitpid(child.pid, &status, 0) == child.pid); child.pid = -1;
  REQUIRE(WIFEXITED(status)); REQUIRE(WEXITSTATUS(status) == 0);
  return wtest::exit_code();
}
