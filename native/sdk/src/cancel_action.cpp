#include "cancel_action.hpp"

namespace gnsdk {

void CancelState::begin_request(std::uint64_t deadline_ms) noexcept {
  flag_.store(false, std::memory_order_relaxed);
  if (deadline_ms == 0) {
    deadline_.reset();
  } else {
    deadline_ = std::chrono::steady_clock::now() + std::chrono::milliseconds(deadline_ms);
  }
}

void CancelState::check() const {
  if (flag_.load(std::memory_order_relaxed)) throw CancelledError(false);
  if (deadline_ && std::chrono::steady_clock::now() > *deadline_) throw CancelledError(true);
}

ghidra::Action* ActionCancelCheck::clone(const ghidra::ActionGroupList& grouplist) const {
  if (!grouplist.contains(getGroup())) return nullptr;
  return new ActionCancelCheck(state_);
}

ghidra::int4 ActionCancelCheck::apply(ghidra::Funcdata& /*data*/) {
  state_->check();
  return 0;
}

bool install_cancel_action(ghidra::Architecture& arch, const CancelState* state) {
  ghidra::Action* root = arch.allacts.getCurrent();
  if (root == nullptr) return false;
  // Group names come from ActionDatabase::universalAction (coreaction.cc).
  ghidra::Action* loop = root->getSubAction("universal::fullloop::mainloop");
  if (loop == nullptr) return false;
  auto* group = dynamic_cast<ghidra::ActionGroup*>(loop);
  if (group == nullptr) return false;
  if (group->getSubAction(std::string(ActionCancelCheck::kName)) != nullptr) return true;  // already there
  group->addAction(new ActionCancelCheck(state));  // the group owns and deletes it
  return true;
}

}  // namespace gnsdk
