// json_min.cpp - see json_min.hpp.
#include "json_min.hpp"

#include <charconv>
#include <cmath>
#include <cstring>
#include <limits>

namespace gnsdk::json {

namespace {

const std::string& empty_string() {
  static const std::string s;
  return s;
}

bool is_ws(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }

void append_utf8(std::uint32_t cp, std::string& out) {
  if (cp < 0x80) {
    out.push_back(static_cast<char>(cp));
  } else if (cp < 0x800) {
    out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
    out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
  } else if (cp < 0x10000) {
    out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
    out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
    out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
  } else {
    out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
    out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
    out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
    out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
  }
}

// Returns the length of the well-formed UTF-8 sequence starting at s[i], or 0 if malformed.
std::size_t utf8_seq_len(std::string_view s, std::size_t i) {
  const auto b0 = static_cast<unsigned char>(s[i]);
  if (b0 < 0x80) return 1;
  std::size_t n;
  std::uint32_t min_cp;
  std::uint32_t cp;
  if ((b0 & 0xE0) == 0xC0) { n = 2; min_cp = 0x80; cp = b0 & 0x1Fu; }
  else if ((b0 & 0xF0) == 0xE0) { n = 3; min_cp = 0x800; cp = b0 & 0x0Fu; }
  else if ((b0 & 0xF8) == 0xF0) { n = 4; min_cp = 0x10000; cp = b0 & 0x07u; }
  else return 0;
  if (i + n > s.size()) return 0;
  for (std::size_t k = 1; k < n; ++k) {
    const auto b = static_cast<unsigned char>(s[i + k]);
    if ((b & 0xC0) != 0x80) return 0;
    cp = (cp << 6) | (b & 0x3Fu);
  }
  if (cp < min_cp) return 0;                      // overlong
  if (cp > 0x10FFFF) return 0;                    // beyond Unicode
  if (cp >= 0xD800 && cp <= 0xDFFF) return 0;     // surrogate
  return n;
}

class Parser {
 public:
  Parser(std::string_view text, const ParseOptions& opt) : s_(text), opt_(opt) {}

  bool run(Value& out, ParseError* err) {
    skip_ws();
    if (!parse_value(out, 0)) { fill(err); return false; }
    skip_ws();
    if (pos_ != s_.size()) { fail("trailing characters after value"); fill(err); return false; }
    return true;
  }

 private:
  void fill(ParseError* err) const {
    if (err) { err->offset = pos_; err->message = msg_ ? msg_ : "parse error"; }
  }
  bool fail(const char* m) { if (!msg_) msg_ = m; return false; }
  void skip_ws() { while (pos_ < s_.size() && is_ws(s_[pos_])) ++pos_; }
  bool at_end() const { return pos_ >= s_.size(); }
  char peek() const { return s_[pos_]; }

  bool parse_value(Value& out, std::size_t depth) {
    if (at_end()) return fail("unexpected end of input");
    switch (peek()) {
      case '{': return parse_object(out, depth + 1);
      case '[': return parse_array(out, depth + 1);
      case '"': { std::string str; if (!parse_string(str)) return false; out = Value(std::move(str)); return true; }
      case 't': return parse_literal("true", Value(true), out);
      case 'f': return parse_literal("false", Value(false), out);
      case 'n': return parse_literal("null", Value(nullptr), out);
      default:
        if (peek() == '-' || (peek() >= '0' && peek() <= '9')) return parse_number(out);
        return fail("unexpected character");
    }
  }

  bool parse_literal(const char* lit, Value v, Value& out) {
    const std::size_t n = std::strlen(lit);
    if (s_.substr(pos_, n) != lit) return fail("invalid literal");
    pos_ += n;
    out = std::move(v);
    return true;
  }

  bool parse_object(Value& out, std::size_t depth) {
    if (depth > opt_.max_depth) return fail("nesting too deep");
    ++pos_;  // '{'
    out = Value::object();
    skip_ws();
    if (!at_end() && peek() == '}') { ++pos_; return true; }
    for (;;) {
      skip_ws();
      if (at_end() || peek() != '"') return fail("expected object key");
      std::string key;
      if (!parse_string(key)) return false;
      skip_ws();
      if (at_end() || peek() != ':') return fail("expected ':'");
      ++pos_;
      skip_ws();
      Value v;
      if (!parse_value(v, depth)) return false;
      out.push_pair(std::move(key), std::move(v));
      skip_ws();
      if (at_end()) return fail("unterminated object");
      if (peek() == ',') { ++pos_; continue; }
      if (peek() == '}') { ++pos_; return true; }
      return fail("expected ',' or '}'");
    }
  }

  bool parse_array(Value& out, std::size_t depth) {
    if (depth > opt_.max_depth) return fail("nesting too deep");
    ++pos_;  // '['
    out = Value::array();
    skip_ws();
    if (!at_end() && peek() == ']') { ++pos_; return true; }
    for (;;) {
      skip_ws();
      Value v;
      if (!parse_value(v, depth)) return false;
      out.push(std::move(v));
      skip_ws();
      if (at_end()) return fail("unterminated array");
      if (peek() == ',') { ++pos_; continue; }
      if (peek() == ']') { ++pos_; return true; }
      return fail("expected ',' or ']'");
    }
  }

  bool parse_hex4(std::uint32_t& out) {
    if (pos_ + 4 > s_.size()) return fail("truncated \\u escape");
    std::uint32_t v = 0;
    for (int k = 0; k < 4; ++k) {
      const char c = s_[pos_ + static_cast<std::size_t>(k)];
      std::uint32_t d;
      if (c >= '0' && c <= '9') d = static_cast<std::uint32_t>(c - '0');
      else if (c >= 'a' && c <= 'f') d = static_cast<std::uint32_t>(c - 'a' + 10);
      else if (c >= 'A' && c <= 'F') d = static_cast<std::uint32_t>(c - 'A' + 10);
      else return fail("bad hex digit in \\u escape");
      v = (v << 4) | d;
    }
    pos_ += 4;
    out = v;
    return true;
  }

  bool parse_string(std::string& out) {
    ++pos_;  // opening quote
    out.clear();
    for (;;) {
      if (at_end()) return fail("unterminated string");
      const auto c = static_cast<unsigned char>(s_[pos_]);
      if (c == '"') { ++pos_; return true; }
      if (c == '\\') {
        ++pos_;
        if (at_end()) return fail("unterminated escape");
        const char e = s_[pos_++];
        switch (e) {
          case '"': out.push_back('"'); break;
          case '\\': out.push_back('\\'); break;
          case '/': out.push_back('/'); break;
          case 'b': out.push_back('\b'); break;
          case 'f': out.push_back('\f'); break;
          case 'n': out.push_back('\n'); break;
          case 'r': out.push_back('\r'); break;
          case 't': out.push_back('\t'); break;
          case 'u': {
            std::uint32_t cp;
            if (!parse_hex4(cp)) return false;
            if (cp >= 0xD800 && cp <= 0xDBFF) {
              // high surrogate: a low surrogate escape must follow
              if (pos_ + 2 > s_.size() || s_[pos_] != '\\' || s_[pos_ + 1] != 'u') return fail("lone high surrogate");
              pos_ += 2;
              std::uint32_t lo;
              if (!parse_hex4(lo)) return false;
              if (lo < 0xDC00 || lo > 0xDFFF) return fail("invalid low surrogate");
              cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
            } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
              return fail("lone low surrogate");
            }
            append_utf8(cp, out);
            break;
          }
          default: return fail("invalid escape");
        }
        continue;
      }
      if (c < 0x20) return fail("control character in string");
      if (c < 0x80) { out.push_back(static_cast<char>(c)); ++pos_; continue; }
      const std::size_t n = utf8_seq_len(s_, pos_);
      if (n == 0) return fail("invalid UTF-8 in string");
      out.append(s_.data() + pos_, n);
      pos_ += n;
    }
  }

  bool parse_number(Value& out) {
    const std::size_t start = pos_;
    bool is_int = true;
    if (peek() == '-') ++pos_;
    if (at_end()) return fail("bad number");
    if (peek() == '0') {
      ++pos_;
    } else if (peek() >= '1' && peek() <= '9') {
      while (!at_end() && peek() >= '0' && peek() <= '9') ++pos_;
    } else {
      return fail("bad number");
    }
    if (!at_end() && peek() == '.') {
      is_int = false;
      ++pos_;
      if (at_end() || peek() < '0' || peek() > '9') return fail("bad fraction");
      while (!at_end() && peek() >= '0' && peek() <= '9') ++pos_;
    }
    if (!at_end() && (peek() == 'e' || peek() == 'E')) {
      is_int = false;
      ++pos_;
      if (!at_end() && (peek() == '+' || peek() == '-')) ++pos_;
      if (at_end() || peek() < '0' || peek() > '9') return fail("bad exponent");
      while (!at_end() && peek() >= '0' && peek() <= '9') ++pos_;
    }
    const std::string_view tok = s_.substr(start, pos_ - start);
    if (is_int) {
      std::int64_t iv = 0;
      const auto r = std::from_chars(tok.data(), tok.data() + tok.size(), iv);
      if (r.ec == std::errc{} && r.ptr == tok.data() + tok.size()) { out = Value(static_cast<long long>(iv)); return true; }
      // out of int64 range: fall through to double
    }
    double dv = 0.0;
    const auto r = std::from_chars(tok.data(), tok.data() + tok.size(), dv);
    if (r.ec == std::errc::result_out_of_range) {
      // from_chars leaves dv unset on overflow/underflow. Overflow becomes the
      // largest finite double (never inf); underflow (negative exponent) is 0.
      const std::size_t e = tok.find_first_of("eE");
      const bool underflow = e != std::string_view::npos && e + 1 < tok.size() && tok[e + 1] == '-';
      if (underflow) dv = (tok[0] == '-') ? -0.0 : 0.0;
      else dv = (tok[0] == '-') ? -std::numeric_limits<double>::max() : std::numeric_limits<double>::max();
    } else if (r.ec != std::errc{} || r.ptr != tok.data() + tok.size()) {
      return fail("bad number");
    }
    out = Value(dv);
    return true;
  }

  std::string_view s_;
  const ParseOptions& opt_;
  std::size_t pos_ = 0;
  const char* msg_ = nullptr;
};

}  // namespace

Value::Value(unsigned long v) {
  if (v <= static_cast<unsigned long>(std::numeric_limits<std::int64_t>::max())) { type_ = Type::Int; i_ = static_cast<std::int64_t>(v); }
  else { type_ = Type::Double; d_ = static_cast<double>(v); }
}

Value::Value(unsigned long long v) {
  if (v <= static_cast<unsigned long long>(std::numeric_limits<std::int64_t>::max())) { type_ = Type::Int; i_ = static_cast<std::int64_t>(v); }
  else { type_ = Type::Double; d_ = static_cast<double>(v); }
}

std::int64_t Value::as_int(std::int64_t def) const {
  if (type_ == Type::Int) return i_;
  if (type_ == Type::Double && std::isfinite(d_) && d_ == std::floor(d_) &&
      d_ >= -9223372036854775808.0 && d_ < 9223372036854775808.0) {
    return static_cast<std::int64_t>(d_);
  }
  return def;
}

double Value::as_double(double def) const {
  if (type_ == Type::Int) return static_cast<double>(i_);
  if (type_ == Type::Double) return d_;
  return def;
}

const std::string& Value::as_string() const { return type_ == Type::String ? s_ : empty_string(); }

const Value* Value::get(std::string_view key) const {
  if (type_ != Type::Object) return nullptr;
  for (std::size_t i = keys_.size(); i-- > 0;) {
    if (keys_[i] == key) return &items_[i];
  }
  return nullptr;
}

Value* Value::get(std::string_view key) {
  return const_cast<Value*>(static_cast<const Value*>(this)->get(key));
}

bool Value::get_bool(std::string_view key, bool& out) const {
  const Value* v = get(key);
  if (!v || !v->is_bool()) return false;
  out = v->b_;
  return true;
}

bool Value::get_int(std::string_view key, std::int64_t& out) const {
  const Value* v = get(key);
  if (!v || !v->is_int()) return false;
  out = v->i_;
  return true;
}

bool Value::get_uint(std::string_view key, std::uint64_t& out) const {
  const Value* v = get(key);
  if (!v || !v->is_int() || v->i_ < 0) return false;
  out = static_cast<std::uint64_t>(v->i_);
  return true;
}

bool Value::get_double(std::string_view key, double& out) const {
  const Value* v = get(key);
  if (!v || !v->is_number()) return false;
  out = v->as_double();
  return true;
}

bool Value::get_string(std::string_view key, std::string& out) const {
  const Value* v = get(key);
  if (!v || !v->is_string()) return false;
  out = v->s_;
  return true;
}

const Value* Value::get_array(std::string_view key) const {
  const Value* v = get(key);
  return (v && v->is_array()) ? v : nullptr;
}

const Value* Value::get_object(std::string_view key) const {
  const Value* v = get(key);
  return (v && v->is_object()) ? v : nullptr;
}

Value& Value::set(std::string key, Value v) {
  if (type_ == Type::Null) type_ = Type::Object;
  if (type_ != Type::Object) return *this;
  for (std::size_t i = keys_.size(); i-- > 0;) {
    if (keys_[i] == key) { items_[i] = std::move(v); return *this; }
  }
  keys_.push_back(std::move(key));
  items_.push_back(std::move(v));
  return *this;
}

void Value::push_pair(std::string key, Value v) {
  keys_.push_back(std::move(key));
  items_.push_back(std::move(v));
}

Value& Value::push(Value v) {
  if (type_ == Type::Null) type_ = Type::Array;
  if (type_ != Type::Array) return *this;
  items_.push_back(std::move(v));
  return *this;
}

void Value::clear() {
  keys_.clear();
  items_.clear();
  s_.clear();
  b_ = false;
  i_ = 0;
  d_ = 0.0;
}

void escape_string(std::string_view s, std::string& out) {
  static const char kHex[] = "0123456789abcdef";
  out.push_back('"');
  for (const char ch : s) {
    const auto c = static_cast<unsigned char>(ch);
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\b': out += "\\b"; break;
      case '\f': out += "\\f"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (c < 0x20 || c == 0x7F) {
          out += "\\u00";
          out.push_back(kHex[c >> 4]);
          out.push_back(kHex[c & 0xF]);
        } else {
          out.push_back(ch);
        }
    }
  }
  out.push_back('"');
}

bool validate_utf8(std::string_view s) {
  std::size_t i = 0;
  while (i < s.size()) {
    const std::size_t n = utf8_seq_len(s, i);
    if (n == 0) return false;
    i += n;
  }
  return true;
}

void Value::dump_to(std::string& out) const {
  switch (type_) {
    case Type::Null: out += "null"; break;
    case Type::Bool: out += b_ ? "true" : "false"; break;
    case Type::Int: {
      char buf[32];
      const auto r = std::to_chars(buf, buf + sizeof buf, i_);
      out.append(buf, static_cast<std::size_t>(r.ptr - buf));
      break;
    }
    case Type::Double: {
      if (!std::isfinite(d_)) { out += "null"; break; }
      char buf[64];
      const auto r = std::to_chars(buf, buf + sizeof buf, d_);
      out.append(buf, static_cast<std::size_t>(r.ptr - buf));
      break;
    }
    case Type::String: escape_string(s_, out); break;
    case Type::Array:
      out.push_back('[');
      for (std::size_t i = 0; i < items_.size(); ++i) {
        if (i) out.push_back(',');
        items_[i].dump_to(out);
      }
      out.push_back(']');
      break;
    case Type::Object:
      out.push_back('{');
      for (std::size_t i = 0; i < items_.size(); ++i) {
        if (i) out.push_back(',');
        escape_string(keys_[i], out);
        out.push_back(':');
        items_[i].dump_to(out);
      }
      out.push_back('}');
      break;
  }
}

std::string Value::dump() const {
  std::string out;
  dump_to(out);
  return out;
}

bool parse(std::string_view text, Value& out, ParseError* err, const ParseOptions& opt) {
  if (text.size() > opt.max_bytes) {
    if (err) { err->offset = 0; err->message = "input exceeds size limit"; }
    return false;
  }
  Parser p(text, opt);
  Value v;
  if (!p.run(v, err)) return false;
  out = std::move(v);
  return true;
}

}  // namespace gnsdk::json
