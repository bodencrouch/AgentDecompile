// json_min.hpp - minimal JSON value, parser and serializer for the gnsdk worker protocol.
//
// Scope (deliberately small, no third-party code):
//   * objects, arrays, strings, integers (int64), doubles, bools, null
//   * string escapes incl. \uXXXX with UTF-16 surrogate pairs -> UTF-8
//   * strict UTF-8: invalid byte sequences inside strings are a parse error;
//     valid multi-byte sequences pass through unchanged
//   * nesting depth limit (default 64) and input size limit (caller supplied)
//   * numbers: integer literals that fit int64 become Int; anything with a
//     fraction/exponent or outside int64 becomes Double. NaN/Inf never parse;
//     non-finite doubles serialize as null.
//   * duplicate object keys are kept in order; lookups return the LAST match.
//
// Single-threaded use only (no shared state, but no internal locking either).
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace gnsdk::json {

enum class Type : std::uint8_t { Null, Bool, Int, Double, String, Array, Object };

class Value {
 public:
  Value() = default;
  Value(std::nullptr_t) {}  // NOLINT(google-explicit-constructor)
  Value(bool b) : type_(Type::Bool), b_(b) {}  // NOLINT
  Value(int v) : type_(Type::Int), i_(v) {}  // NOLINT
  Value(long v) : type_(Type::Int), i_(v) {}  // NOLINT
  Value(long long v) : type_(Type::Int), i_(v) {}  // NOLINT
  Value(unsigned v) : type_(Type::Int), i_(static_cast<std::int64_t>(v)) {}  // NOLINT
  Value(unsigned long v);  // NOLINT  Int if it fits, else Double
  Value(unsigned long long v);  // NOLINT
  Value(double d) : type_(Type::Double), d_(d) {}  // NOLINT
  Value(std::string s) : type_(Type::String), s_(std::move(s)) {}  // NOLINT
  Value(std::string_view s) : type_(Type::String), s_(s) {}  // NOLINT
  Value(const char* s) : type_(Type::String), s_(s ? s : "") {}  // NOLINT

  static Value array() { Value v; v.type_ = Type::Array; return v; }
  static Value object() { Value v; v.type_ = Type::Object; return v; }

  Type type() const { return type_; }
  bool is_null() const { return type_ == Type::Null; }
  bool is_bool() const { return type_ == Type::Bool; }
  bool is_int() const { return type_ == Type::Int; }
  bool is_double() const { return type_ == Type::Double; }
  bool is_number() const { return type_ == Type::Int || type_ == Type::Double; }
  bool is_string() const { return type_ == Type::String; }
  bool is_array() const { return type_ == Type::Array; }
  bool is_object() const { return type_ == Type::Object; }

  bool as_bool(bool def = false) const { return is_bool() ? b_ : def; }
  std::int64_t as_int(std::int64_t def = 0) const;   // Int, or integral finite Double
  double as_double(double def = 0.0) const;          // Int or Double
  const std::string& as_string() const;              // empty string if not a string

  // Arrays and objects.
  std::size_t size() const { return items_.size(); }
  bool empty() const { return items_.empty(); }
  const Value& operator[](std::size_t i) const { return items_[i]; }
  Value& operator[](std::size_t i) { return items_[i]; }
  const std::vector<Value>& items() const { return items_; }
  const std::vector<std::string>& keys() const { return keys_; }

  // Objects: nullptr when absent or not an object.
  const Value* get(std::string_view key) const;
  Value* get(std::string_view key);
  bool has(std::string_view key) const { return get(key) != nullptr; }
  // Typed lookups; return false (and leave `out` untouched) if absent or wrong type.
  bool get_bool(std::string_view key, bool& out) const;
  bool get_int(std::string_view key, std::int64_t& out) const;
  bool get_uint(std::string_view key, std::uint64_t& out) const;  // rejects negatives
  bool get_double(std::string_view key, double& out) const;
  bool get_string(std::string_view key, std::string& out) const;
  const Value* get_array(std::string_view key) const;
  const Value* get_object(std::string_view key) const;

  // Builders. set() turns a Null into an Object; push() turns a Null into an Array.
  Value& set(std::string key, Value v);   // replaces the last existing key or appends
  Value& push(Value v);
  void push_pair(std::string key, Value v);  // append without duplicate check (parser use)
  void clear();

  std::string dump() const;
  void dump_to(std::string& out) const;

 private:
  Type type_ = Type::Null;
  bool b_ = false;
  std::int64_t i_ = 0;
  double d_ = 0.0;
  std::string s_;
  std::vector<std::string> keys_;  // object keys, parallel to items_
  std::vector<Value> items_;       // array items or object values
};

struct ParseOptions {
  std::size_t max_depth = 64;                  // nesting levels of arrays/objects
  std::size_t max_bytes = 64u * 1024u * 1024u; // reject longer inputs outright
};

struct ParseError {
  std::size_t offset = 0;
  const char* message = "";
};

// Parses exactly one JSON value; trailing whitespace is allowed, anything else is an error.
// Never throws; returns false and fills `err` (if given) on failure.
bool parse(std::string_view text, Value& out, ParseError* err = nullptr,
           const ParseOptions& opt = ParseOptions{});

// Appends the JSON string literal (with quotes) for `s` to `out`.
void escape_string(std::string_view s, std::string& out);
// True if `s` is well-formed UTF-8 (no overlongs, no surrogates, max U+10FFFF).
bool validate_utf8(std::string_view s);

}  // namespace gnsdk::json
