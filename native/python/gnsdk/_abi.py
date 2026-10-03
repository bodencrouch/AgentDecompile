"""ctypes declarations for gnsdk.h ABI 0.1.0."""

import ctypes as c

ABI_MAJOR = 0


class Buf(c.Structure):
    _fields_ = [("data", c.POINTER(c.c_uint8)), ("len", c.c_size_t), ("format", c.c_uint32),
               ("_reserved", c.c_uint32), ("_owner", c.c_void_p)]


class VersionInfo(c.Structure):
    _fields_ = [("struct_size", c.c_uint32), ("abi_major", c.c_uint32), ("abi_minor", c.c_uint32),
               ("abi_patch", c.c_uint32), ("sla_format_version", c.c_uint32), ("_reserved", c.c_uint32),
               ("ghidra_version", c.c_char * 32), ("source", c.c_char * 64),
               ("engine_hash", c.c_char * 48), ("build_flags", c.c_char * 128),
               ("engine_sig_major", c.c_uint32), ("engine_sig_minor", c.c_uint32)]


class InitOptions(c.Structure):
    _fields_ = [("struct_size", c.c_uint32), ("flags", c.c_uint32), ("sleigh_home", c.c_char_p)]


class SessionOptions(c.Structure):
    _fields_ = [("struct_size", c.c_uint32), ("flags", c.c_uint32), ("language_id", c.c_char_p)]


class ImageDesc(c.Structure):
    _fields_ = [("struct_size", c.c_uint32), ("flags", c.c_uint32), ("bytes", c.POINTER(c.c_uint8)),
               ("len", c.c_size_t), ("base", c.c_uint64), ("name", c.c_char_p)]


class DecompileOptions(c.Structure):
    _fields_ = [("struct_size", c.c_uint32), ("flags", c.c_uint32), ("deadline_ms", c.c_uint64),
               ("max_instructions", c.c_uint32), ("want_tokens", c.c_uint32), ("printer", c.c_uint32),
               ("follow_flow_limit", c.c_uint32), ("options_xml", c.c_char_p), ("function_name", c.c_char_p)]


class DecompileOut(c.Structure):
    _fields_ = [("struct_size", c.c_uint32), ("status_detail", c.c_int32),
               ("c_text", Buf), ("tokens", Buf), ("warnings", Buf)]


SessionHandle = c.c_void_p


def sized(value: c.Structure) -> c.Structure:
    value.struct_size = c.sizeof(value)
    return value
