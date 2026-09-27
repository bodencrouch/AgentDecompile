"""Parameter types the MCP server advertises for every tool (tools/list inputSchema).

Generated commands in cli.py take their click option types from this table so
the CLI rejects what the server would reject: an ``integer`` param such as
``run-decomp-match --timeout`` must not accept ``abc`` and send a string the
server then silently replaces with its default (``_coerce_int``). Keys are
canonical tool names; param keys are ``normalize_identifier`` forms. Values are
JSON-schema types: integer, number, boolean, array, string.

Source: ``ToolProviderManager.list_tools()`` (provider inputSchema first, then
``_infer_param_schema``), widened to every Tool and every TOOL_PARAMS name.
Kept as data so the CLI does not import mcp_server at startup.

Drift guard (in memory, no JVM, no network; run it by hand after changing a
provider schema or TOOL_PARAMS -- nothing runs it on a schedule)::

    PYTHONPATH=src python -m agentdecompile_cli.cli_param_types --check
    PYTHONPATH=src python -m agentdecompile_cli.cli_param_types --write

``--check`` prints every added, removed or retyped param and exits 1 on drift.
``--write`` rewrites the table below from the same regeneration.
"""

from __future__ import annotations

ADVERTISED_PARAM_TYPES: dict[str, dict[str, str]] = {
    "acquisition-query": {
        "address": "string",
        "bundledir": "string",
        "limit": "integer",
        "mode": "string",
        "query": "string",
    },
    "analyze-data-flow": {
        "addressorsymbol": "string",
        "direction": "string",
        "functionaddress": "string",
        "functionidentifier": "string",
        "maxdepth": "integer",
        "maxops": "integer",
        "programpath": "string",
        "startaddress": "string",
        "timeout": "integer",
        "variablename": "string",
    },
    "analyze-program": {
        "analyzers": "array",
        "force": "boolean",
        "programpath": "string",
    },
    "analyze-vtables": {
        "addressorsymbol": "string",
        "functionaddress": "string",
        "limit": "integer",
        "maxentries": "integer",
        "maxresults": "integer",
        "mode": "string",
        "programpath": "string",
        "vtableaddress": "string",
    },
    "apply-data-type": {
        "addressorsymbol": "string",
        "archivename": "string",
        "datatype": "string",
        "datatypestring": "string",
        "programpath": "string",
    },
    "bsim-createdatabase": {
        "bsimurl": "string",
        "datadir": "string",
        "description": "string",
        "name": "string",
        "owner": "string",
        "template": "string",
    },
    "bsim-ingest": {
        "bsimurl": "string",
        "datadir": "string",
        "force": "boolean",
        "ghidraurl": "string",
        "name": "string",
        "programs": "array",
        "receipt": "string",
        "repository": "string",
    },
    "bsim-report": {
        "bsimurl": "string",
        "datadir": "string",
        "name": "string",
    },
    "change-processor": {
        "compiler": "string",
        "compilerspecid": "string",
        "endian": "string",
        "language": "string",
        "languageid": "string",
        "processor": "string",
        "programpath": "string",
    },
    "checkin-program": {
        "comment": "string",
        "format": "string",
        "keepcheckedout": "boolean",
        "programpath": "string",
    },
    "checkout-program": {
        "exclusive": "boolean",
        "format": "string",
        "programpath": "string",
    },
    "checkout-status": {
        "format": "string",
        "programpath": "string",
    },
    "claim-report": {
        "terminalstatus": "string",
        "workdir": "string",
        "write": "boolean",
    },
    "create-label": {
        "addressorsymbol": "string",
        "labelname": "string",
        "programpath": "string",
        "setasprimary": "boolean",
    },
    "decompile-function": {
        "addressorsymbol": "string",
        "function": "string",
        "functionidentifier": "string",
        "functions": "string",
        "includecallees": "boolean",
        "includecallers": "boolean",
        "includecomments": "boolean",
        "includedisassembly": "boolean",
        "includeincomingreferences": "boolean",
        "includereferencecontext": "string",
        "includestrings": "boolean",
        "includexrefs": "boolean",
        "limit": "integer",
        "nameoraddress": "string",
        "offset": "integer",
        "programpath": "string",
        "showunreachable": "boolean",
        "signatureonly": "string",
        "timeout": "integer",
    },
    "delete-project-binary": {
        "confirm": "boolean",
        "programpath": "string",
    },
    "execute-script": {
        "code": "string",
        "programpath": "string",
        "timeout": "integer",
    },
    "export": {
        "createheader": "boolean",
        "format": "string",
        "includecomments": "boolean",
        "includeglobals": "boolean",
        "includetypes": "boolean",
        "outputpath": "string",
        "programpath": "string",
        "recoverylanguage": "string",
        "sourcelanguage": "string",
        "tags": "string",
    },
    "export-context": {
        "binaryanalysis": "string",
        "extractcontainers": "boolean",
        "format": "string",
        "includelowsignalmembers": "boolean",
        "inputpath": "string",
        "maxdepth": "integer",
        "maxfiles": "integer",
        "outdir": "string",
    },
    "gen-callgraph": {
        "bottomlayers": "integer",
        "condensethreshold": "integer",
        "depth": "integer",
        "direction": "string",
        "displaytype": "string",
        "format": "string",
        "functionidentifier": "string",
        "includerefs": "boolean",
        "maxdepth": "integer",
        "maxruntime": "integer",
        "programpath": "string",
        "toplayers": "integer",
    },
    "get-call-graph": {
        "addressorsymbol": "string",
        "bottomlayers": "integer",
        "condensethreshold": "integer",
        "depth": "integer",
        "direction": "string",
        "displaytype": "string",
        "function": "string",
        "functionaddresses": "string",
        "functionidentifier": "string",
        "includecallcontext": "boolean",
        "includerefs": "boolean",
        "maxcallers": "integer",
        "maxdepth": "integer",
        "maxnodes": "integer",
        "maxruntime": "integer",
        "mode": "string",
        "programpath": "string",
        "secondfunction": "string",
        "startindex": "integer",
        "toplayers": "integer",
    },
    "get-current-address": {
        "programpath": "string",
    },
    "get-current-function": {
        "programpath": "string",
    },
    "get-current-program": {
        "programpath": "string",
    },
    "get-data": {
        "addressorsymbol": "string",
        "format": "string",
        "length": "integer",
        "programpath": "string",
        "view": "string",
    },
    "get-function": {
        "addressorsymbol": "string",
        "calleebranching": "integer",
        "calleedepth": "integer",
        "callerbranching": "integer",
        "callerdepth": "integer",
        "dataflowaddress": "string",
        "dataflowdirection": "string",
        "dataflowmaxdepth": "integer",
        "dataflowmaxops": "integer",
        "function": "string",
        "functionidentifier": "string",
        "functions": "string",
        "maxcallees": "integer",
        "maxcallers": "integer",
        "maxinstructions": "integer",
        "maxrefs": "integer",
        "maxrelatedcallees": "integer",
        "maxrelatedcallers": "integer",
        "mode": "string",
        "programpath": "string",
        "timeout": "integer",
        "view": "string",
    },
    "get-functions": {
        "addressorsymbol": "string",
        "filterbytag": "string",
        "filterdefaultnames": "boolean",
        "function": "string",
        "functions": "string",
        "identifier": "string",
        "includecallees": "boolean",
        "includecallers": "boolean",
        "includecomments": "boolean",
        "includeincomingreferences": "boolean",
        "includereferencecontext": "string",
        "limit": "integer",
        "mode": "string",
        "offset": "integer",
        "programpath": "string",
        "timeout": "integer",
        "untagged": "boolean",
        "verbose": "boolean",
        "view": "string",
    },
    "get-references": {
        "addressorsymbol": "string",
        "contextlines": "string",
        "direction": "string",
        "importname": "string",
        "includedatarefs": "string",
        "includeflow": "boolean",
        "includerefcontext": "boolean",
        "libraryname": "string",
        "limit": "integer",
        "maxreferencers": "integer",
        "mode": "string",
        "offset": "integer",
        "programpath": "string",
        "startindex": "integer",
        "target": "string",
    },
    "import-binary": {
        "analyzeafterimport": "boolean",
        "compiler": "string",
        "destinationfolder": "string",
        "enableversioncontrol": "boolean",
        "filepath": "string",
        "language": "string",
        "maxdepth": "integer",
        "mirrorfs": "boolean",
        "path": "string",
        "programname": "string",
        "programpath": "string",
        "recursive": "boolean",
        "stripallcontainerpath": "boolean",
        "stripleadingpath": "boolean",
    },
    "inspect-memory": {
        "address": "string",
        "addressorsymbol": "string",
        "direction": "string",
        "kind": "string",
        "length": "integer",
        "limit": "integer",
        "maxresults": "integer",
        "mode": "string",
        "offset": "integer",
        "programpath": "string",
    },
    "list-cross-references": {
        "address": "string",
        "addressorsymbol": "string",
        "direction": "string",
        "importname": "string",
        "limit": "integer",
        "maxresults": "integer",
        "offset": "integer",
        "programpath": "string",
        "target": "string",
    },
    "list-exports": {
        "filter": "string",
        "limit": "integer",
        "maxresults": "integer",
        "offset": "integer",
        "programpath": "string",
        "startindex": "integer",
    },
    "list-fallback-projects": {
        "originalprojectname": "string",
        "projectsdir": "string",
    },
    "list-functions": {
        "addressmax": "string",
        "addressmin": "string",
        "callingconvention": "string",
        "filterbytag": "string",
        "filterdefaultnames": "boolean",
        "hastags": "boolean",
        "identifiers": "string",
        "includeexternals": "boolean",
        "inline": "boolean",
        "limit": "integer",
        "maxcount": "integer",
        "maxsize": "integer",
        "minreferencecount": "integer",
        "minsize": "integer",
        "mode": "string",
        "namepattern": "string",
        "offset": "integer",
        "pattern": "string",
        "programpath": "string",
        "query": "string",
        "searchstring": "string",
        "signaturepattern": "string",
        "startindex": "integer",
        "undefinedparameters": "boolean",
        "untagged": "boolean",
        "verbose": "boolean",
    },
    "list-imports": {
        "groupbylibrary": "boolean",
        "libraryfilter": "string",
        "limit": "integer",
        "maxresults": "integer",
        "offset": "integer",
        "programpath": "string",
        "query": "string",
        "startindex": "integer",
    },
    "list-processors": {
        "filter": "string",
    },
    "list-project-files": {
        "binary": "string",
        "folder": "string",
        "maxresults": "integer",
        "path": "string",
        "programpath": "string",
    },
    "list-strings": {
        "filter": "string",
        "includereferencingfunctions": "boolean",
        "limit": "integer",
        "maxresults": "integer",
        "minlength": "integer",
        "offset": "integer",
        "programpath": "string",
    },
    "manage-bookmarks": {
        "addressorsymbol": "string",
        "addressrange": "string",
        "bookmarks": "array",
        "categories": "string",
        "category": "string",
        "comment": "string",
        "confirmremoveall": "boolean",
        "limit": "integer",
        "maxresults": "integer",
        "mode": "string",
        "offset": "integer",
        "programpath": "string",
        "query": "string",
        "removeall": "boolean",
        "removealltoken": "string",
        "searchtext": "string",
        "types": "string",
    },
    "manage-comments": {
        "addressorsymbol": "string",
        "addressrange": "string",
        "casesensitive": "boolean",
        "comment": "string",
        "comments": "array",
        "commenttype": "string",
        "commenttypes": "string",
        "end": "string",
        "function": "string",
        "limit": "integer",
        "linenumber": "integer",
        "maxresults": "integer",
        "mode": "string",
        "offset": "integer",
        "overridemaxfunctionslimit": "boolean",
        "pattern": "string",
        "programpath": "string",
        "query": "string",
        "searchtext": "string",
        "start": "string",
    },
    "manage-data-types": {
        "addressorsymbol": "string",
        "archivename": "string",
        "categorypath": "string",
        "datatypestring": "string",
        "description": "string",
        "discovertypes": "boolean",
        "includesubcategories": "boolean",
        "limit": "integer",
        "maxcount": "integer",
        "mode": "string",
        "name": "string",
        "newname": "string",
        "offset": "integer",
        "programpath": "string",
        "startindex": "integer",
    },
    "manage-enums": {
        "categorypath": "string",
        "description": "string",
        "enumname": "string",
        "filter": "string",
        "maxresults": "integer",
        "membername": "string",
        "members": "array",
        "membervalue": "integer",
        "mode": "string",
        "name": "string",
        "namefilter": "string",
        "newmembername": "string",
        "programpath": "string",
        "query": "string",
        "value": "integer",
    },
    "manage-files": {
        "analyzeafterimport": "boolean",
        "compilerspecid": "string",
        "content": "string",
        "createparents": "boolean",
        "destinationfolder": "string",
        "destinationpath": "string",
        "dryrun": "boolean",
        "enableversioncontrol": "boolean",
        "encoding": "string",
        "endian": "string",
        "exclusive": "boolean",
        "exporttype": "string",
        "extensions": "array",
        "filepath": "string",
        "force": "boolean",
        "format": "string",
        "includecomments": "boolean",
        "includeparameters": "boolean",
        "includevariables": "boolean",
        "keep": "boolean",
        "languageid": "string",
        "maxdepth": "integer",
        "maxresults": "integer",
        "mirrorfs": "boolean",
        "mode": "string",
        "newname": "string",
        "newpath": "string",
        "path": "string",
        "processor": "string",
        "programpath": "string",
        "recursive": "boolean",
        "sourcepath": "string",
        "stripallcontainerpath": "boolean",
        "stripleadingpath": "boolean",
        "syncdirection": "string",
    },
    "manage-function": {
        "address": "string",
        "addressorsymbol": "string",
        "archivename": "string",
        "callfixup": "string",
        "callingconvention": "string",
        "createifnotexists": "boolean",
        "customstorage": "boolean",
        "datatypemappings": "string",
        "function": "string",
        "functionidentifier": "string",
        "functions": "string",
        "inline": "boolean",
        "mode": "string",
        "name": "string",
        "namespace": "string",
        "newname": "string",
        "newtype": "string",
        "noreturn": "boolean",
        "oldname": "string",
        "parameterstorage": "array",
        "programpath": "string",
        "propagate": "boolean",
        "propagatemaxcandidates": "integer",
        "propagatemaxinstructions": "integer",
        "propagateprogrampaths": "array",
        "prototype": "string",
        "returnstorage": "array",
        "returntype": "string",
        "thunktarget": "string",
        "varargs": "boolean",
        "variablemappings": "string",
        "variablename": "string",
    },
    "manage-function-tags": {
        "addressorsymbol": "string",
        "function": "string",
        "mode": "string",
        "programpath": "string",
        "tag": "string",
        "tagname": "string",
        "tags": "string",
    },
    "manage-strings": {
        "addressorsymbol": "string",
        "encoding": "string",
        "filter": "string",
        "includereferencingfunctions": "boolean",
        "limit": "integer",
        "maxcount": "integer",
        "minlength": "integer",
        "mode": "string",
        "offset": "integer",
        "pattern": "string",
        "programpath": "string",
        "query": "string",
        "searchstring": "string",
        "startindex": "integer",
        "value": "string",
    },
    "manage-structures": {
        "addressorsymbol": "string",
        "bitfield": "string",
        "category": "string",
        "categorypath": "string",
        "cdefinition": "string",
        "clearexisting": "boolean",
        "comment": "string",
        "datatype": "string",
        "description": "string",
        "fieldcomment": "string",
        "fieldname": "string",
        "fieldoffset": "integer",
        "fields": "array",
        "fieldtype": "string",
        "filter": "string",
        "force": "boolean",
        "headercontent": "string",
        "includebuiltin": "boolean",
        "isunion": "boolean",
        "maxresults": "integer",
        "mode": "string",
        "name": "string",
        "namefilter": "string",
        "newcomment": "string",
        "newdatatype": "string",
        "newfieldname": "string",
        "newlength": "string",
        "offset": "integer",
        "packed": "boolean",
        "programpath": "string",
        "query": "string",
        "size": "integer",
        "structurename": "string",
    },
    "manage-symbols": {
        "address": "string",
        "addressorsymbol": "string",
        "demangleall": "boolean",
        "filterdefaultnames": "boolean",
        "groupbylibrary": "boolean",
        "includeexternal": "boolean",
        "labelname": "string",
        "libraryfilter": "string",
        "limit": "integer",
        "maxcount": "integer",
        "mode": "string",
        "newname": "string",
        "offset": "integer",
        "programpath": "string",
        "query": "string",
        "startindex": "integer",
    },
    "manage-workflow": {
        "jobid": "string",
        "locator": "string",
        "operation": "string",
        "preparationid": "string",
        "priority": "integer",
        "program": "string",
        "seconds": "integer",
        "slug": "string",
        "unlimited": "boolean",
    },
    "match-function": {
        "addressorsymbol": "string",
        "batchsize": "string",
        "filterbytag": "string",
        "filterdefaultnames": "boolean",
        "function": "string",
        "functionidentifier": "string",
        "maxfunctions": "integer",
        "maxinstructions": "integer",
        "maxresults": "integer",
        "minsimilarity": "number",
        "mode": "string",
        "programpath": "string",
        "propagatebookmarks": "boolean",
        "propagatecomments": "boolean",
        "propagatenames": "boolean",
        "propagateprototype": "boolean",
        "propagatetags": "boolean",
        "targetprogrampaths": "array",
    },
    "migrate-metadata": {
        "includeexternals": "boolean",
        "limit": "integer",
        "minsimilarity": "number",
        "programpath": "string",
        "propagatebookmarks": "boolean",
        "propagatecomments": "boolean",
        "propagatenames": "boolean",
        "propagateprototype": "boolean",
        "propagatetags": "boolean",
        "targetprogrampaths": "array",
    },
    "open": {
        "analyzeafterimport": "boolean",
        "destinationfolder": "string",
        "enableversioncontrol": "boolean",
        "extensions": "string",
        "openallprograms": "boolean",
        "path": "string",
        "repositoryname": "string",
        "serverhost": "string",
        "serverpassword": "string",
        "serverport": "integer",
        "serverusername": "string",
        "shared": "boolean",
    },
    "open-all-programs-in-code-browser": {
        "extensions": "string",
        "folderpath": "string",
    },
    "open-program-in-code-browser": {
        "programpath": "string",
    },
    "read-bytes": {
        "address": "string",
        "addressorsymbol": "string",
        "binaryname": "string",
        "length": "integer",
        "programpath": "string",
        "size": "integer",
    },
    "read-workspace-activity": {
        "locator": "string",
        "slug": "string",
    },
    "reconstruct": {
        "acquisitionbundle": "string",
        "autonomous": "boolean",
        "binarypath": "string",
        "contextpack": "string",
        "contextpaths": "array",
        "force": "boolean",
        "preferredname": "string",
        "resume": "boolean",
        "stopafter": "string",
        "workdir": "string",
    },
    "reintegrate-fallback-projects": {
        "deleteaftermerge": "boolean",
        "dryrun": "boolean",
        "fallbackprojectnames": "array",
        "mergemode": "string",
        "originalprojectname": "string",
        "projectsdir": "string",
    },
    "remove-program-binary": {
        "confirm": "boolean",
        "programpath": "string",
    },
    "resolve-modification-conflict": {
        "conflictid": "string",
        "programpath": "string",
        "resolution": "string",
    },
    "run-batch-bsim-signatures": {
        "binarypath": "string",
        "bsimcategories": "array",
        "bsimsigpath": "string",
        "bsimtemplate": "string",
        "forceanalysis": "boolean",
        "functionfilter": "string",
        "outputpath": "string",
        "projectpath": "string",
    },
    "run-batch-decompile": {
        "binarypath": "string",
        "callgraphs": "boolean",
        "forceanalysis": "boolean",
        "functionfilter": "string",
        "outputpath": "string",
        "projectpath": "string",
        "skipcache": "boolean",
        "threadcount": "integer",
    },
    "run-batch-export-gzf": {
        "binarypath": "string",
        "forceanalysis": "boolean",
        "gzfpath": "string",
        "outputpath": "string",
        "projectpath": "string",
        "skipsymbols": "boolean",
    },
    "run-batch-sast-scan": {
        "binarypath": "string",
        "codeqlrules": "string",
        "forceanalysis": "boolean",
        "functionfilter": "string",
        "outputpath": "string",
        "projectpath": "string",
        "semgreprules": "array",
    },
    "run-decomp-match": {
        "assemblypath": "string",
        "baseobjectpath": "string",
        "contextpath": "string",
        "extraargs": "array",
        "functionname": "string",
        "jobs": "integer",
        "objdiffmode": "string",
        "outputlimit": "integer",
        "permuterdir": "string",
        "permuterscript": "string",
        "projectpath": "string",
        "symbol": "string",
        "target": "string",
        "targetobjectpath": "string",
        "timeout": "integer",
        "tool": "string",
        "tools": "array",
        "unitname": "string",
    },
    "run-external-re-scan": {
        "binarypath": "string",
        "outputlimit": "integer",
        "rulespath": "string",
        "timeout": "integer",
        "tool": "string",
        "tools": "array",
    },
    "run-file-triage": {
        "binarypath": "string",
        "externalscantools": "array",
        "rulespath": "string",
        "scanoutputlimit": "integer",
        "scantimeout": "integer",
        "stringfilter": "string",
        "stringlimit": "integer",
        "timeout": "integer",
        "trybinwalk": "boolean",
        "trycapa": "boolean",
        "tryyara": "boolean",
    },
    "search-code": {
        "binaryname": "string",
        "casesensitive": "boolean",
        "includefullcode": "boolean",
        "limit": "integer",
        "maxresults": "string",
        "offset": "integer",
        "overridemaxfunctionslimit": "boolean",
        "pattern": "string",
        "previewlength": "string",
        "programpath": "string",
        "query": "string",
        "searchmode": "string",
        "similaritythreshold": "string",
    },
    "search-constants": {
        "includesmallvalues": "boolean",
        "limit": "integer",
        "maxinstructions": "integer",
        "maxresults": "integer",
        "maxvalue": "integer",
        "minvalue": "integer",
        "mode": "string",
        "offset": "integer",
        "programpath": "string",
        "samplesperconstant": "integer",
        "topn": "integer",
        "value": "integer",
    },
    "search-everything": {
        "binaryname": "string",
        "casesensitive": "boolean",
        "decompiletimeout": "integer",
        "groupbyfunction": "boolean",
        "limit": "integer",
        "maxfunctionsscan": "integer",
        "maxinstructionsscan": "integer",
        "mode": "string",
        "offset": "integer",
        "perscopelimit": "integer",
        "programname": "string",
        "programpath": "string",
        "queries": "string",
        "query": "string",
        "scopes": "array",
        "similaritythreshold": "number",
    },
    "search-strings": {
        "includereferencingfunctions": "boolean",
        "limit": "integer",
        "maxresults": "integer",
        "mode": "string",
        "offset": "integer",
        "pattern": "string",
        "programpath": "string",
        "query": "string",
        "searchstring": "string",
    },
    "search-symbols": {
        "filterdefaultnames": "boolean",
        "includeexternal": "boolean",
        "limit": "integer",
        "namepattern": "string",
        "offset": "integer",
        "programpath": "string",
        "query": "string",
    },
    "status": {
        "workdir": "string",
    },
    "suggest": {
        "address": "string",
        "addressorsymbol": "string",
        "datatype": "string",
        "function": "string",
        "functionidentifier": "string",
        "includecallees": "boolean",
        "includecallers": "boolean",
        "maxcontext": "integer",
        "programpath": "string",
        "suggestiontype": "string",
        "variableaddress": "string",
        "variablename": "string",
    },
    "svr-admin": {
        "args": "array",
        "mode": "string",
        "timeoutseconds": "integer",
    },
    "sync-project": {
        "destinationfolder": "string",
        "destinationpath": "string",
        "dryrun": "boolean",
        "force": "boolean",
        "maxresults": "integer",
        "mode": "string",
        "newpath": "string",
        "path": "string",
        "recursive": "boolean",
        "sourcepath": "string",
    },
}


def generate_param_types() -> dict[str, dict[str, str]]:
    """Rebuild the table from the providers' advertised schemas, in memory.

    Widens ADVERTISED_TOOL_PARAMS to every Tool (and every TOOL_PARAMS name)
    on the tool_providers module for this call only, so hidden tools are typed
    too; restores the module attributes afterwards.
    """
    import agentdecompile_cli.mcp_server.tool_providers as tp

    from agentdecompile_cli.registry import ADVERTISED_TOOL_PARAMS, TOOL_PARAMS, Tool, normalize_identifier as n

    all_params: dict[str, list[str]] = {}
    for tool in Tool:
        names = list(ADVERTISED_TOOL_PARAMS.get(tool.value, []))
        seen = {n(x) for x in names}
        names += [p for p in TOOL_PARAMS.get(tool, []) if n(p) not in seen]
        all_params[tool.value] = names

    saved = (tp.ADVERTISED_TOOL_PARAMS, tp.get_advertised_tools_for_list)
    tp.ADVERTISED_TOOL_PARAMS = all_params
    tp.get_advertised_tools_for_list = lambda *a, **k: [t.value for t in Tool]
    try:
        manager = tp.ToolProviderManager()
        manager.register_all_providers()
        tools = manager.list_tools()
    finally:
        tp.ADVERTISED_TOOL_PARAMS, tp.get_advertised_tools_for_list = saved

    out: dict[str, dict[str, str]] = {}
    for tool in tools:
        for key, schema in (tool.inputSchema or {}).get("properties", {}).items():
            if n(key) == "responseformat":
                continue
            ty = schema.get("type") if isinstance(schema, dict) else None
            if isinstance(ty, list):
                ty = next((x for x in ty if x != "null"), None)
            out.setdefault(tool.name, {})[n(key)] = ty or "string"
    return {tool: dict(sorted(params.items())) for tool, params in sorted(out.items())}


def diff_param_types(current: dict[str, dict[str, str]], fresh: dict[str, dict[str, str]]) -> list[str]:
    """One line per difference between the stored table and a regeneration."""
    lines: list[str] = []
    for tool in sorted(set(current) | set(fresh)):
        old, new = current.get(tool), fresh.get(tool)
        if old is None:
            lines.append(f"+ {tool} (new tool: {len(new or {})} params)")
            continue
        if new is None:
            lines.append(f"- {tool} (tool no longer advertised)")
            continue
        for param in sorted(set(old) | set(new)):
            if param not in new:
                lines.append(f"- {tool}.{param} ({old[param]})")
            elif param not in old:
                lines.append(f"+ {tool}.{param} ({new[param]})")
            elif old[param] != new[param]:
                lines.append(f"~ {tool}.{param}: {old[param]} -> {new[param]}")
    return lines


def render_param_types(table: dict[str, dict[str, str]]) -> str:
    """The ``ADVERTISED_PARAM_TYPES = {...}`` source block, in this file's layout."""
    lines = ["ADVERTISED_PARAM_TYPES: dict[str, dict[str, str]] = {"]
    for tool, params in table.items():
        lines.append(f'    "{tool}": {{')
        lines.extend(f'        "{param}": "{ty}",' for param, ty in params.items())
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _write_table(table: dict[str, dict[str, str]]) -> None:
    from pathlib import Path

    path = Path(__file__)
    text = path.read_text(encoding="utf-8")
    head = "ADVERTISED_PARAM_TYPES: dict[str, dict[str, str]] = {\n"
    start = text.index(head)
    end = text.index("\n}\n", start) + len("\n}\n")
    path.write_text(text[:start] + render_param_types(table) + text[end:], encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m agentdecompile_cli.cli_param_types",
        description="Compare ADVERTISED_PARAM_TYPES with the providers' advertised schemas.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Print differences; exit 1 on drift.")
    group.add_argument("--write", action="store_true", help="Rewrite the table in this file.")
    args = parser.parse_args(argv)

    fresh = generate_param_types()
    differences = diff_param_types(ADVERTISED_PARAM_TYPES, fresh)
    if args.write:
        if differences:
            _write_table(fresh)
        print(f"cli_param_types: {len(differences)} difference(s) written." if differences else "cli_param_types: already current.")
        return 0
    if differences:
        print("cli_param_types.ADVERTISED_PARAM_TYPES drifted from the advertised schemas:")
        print("\n".join(differences))
        print("Regenerate with: python -m agentdecompile_cli.cli_param_types --write")
        return 1
    print("cli_param_types: ADVERTISED_PARAM_TYPES matches the advertised schemas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
