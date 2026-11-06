// The only place upstream decompiler headers are included. The directory is
// a SYSTEM include on every gnsdk target so upstream warnings never reach
// -Werror. Never `using namespace ghidra;` (error.hh pulls std names into it).
#pragma once

#include "error.hh"
#include "types.h"
#include "xml.hh"
#include "marshal.hh"
#include "capability.hh"
#include "space.hh"
#include "address.hh"
#include "opcodes.hh"
#include "pcoderaw.hh"
#include "translate.hh"
#include "loadimage.hh"
#include "context.hh"
#include "architecture.hh"
#include "sleigh_arch.hh"
#include "xml_arch.hh"
#include "database.hh"
#include "funcdata.hh"
#include "action.hh"
#include "options.hh"
#include "printlanguage.hh"
