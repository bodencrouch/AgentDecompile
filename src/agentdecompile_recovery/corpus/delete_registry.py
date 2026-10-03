"""Atomic binary removal for the reviewed, deliberately bounded v9 profile.

This module never initializes a store. A future schema or surviving identity
lineage requires a separately reviewed profile, not heuristic provenance cleanup.
The frozen DDL allowlist below comes from store, migrations 1-9 and the optional
writers named in next-delete-registry-contract.md. It is inspection data only;
none of it is executed by removal or by open_for_delete.
"""
from __future__ import annotations

import pathlib
import re
import sqlite3
import uuid
from dataclasses import dataclass

from . import match_review_schema


class BinaryDeleteUnsupported(ValueError):
    """Stable preflight refusal: reason prefix followed by the offending object."""

    def __init__(self, reason: str, name: str) -> None:
        super().__init__(f"binary_delete_{reason}:{name}")


# Frozen source declarations, not a dynamically inferred ownership policy.
TABLE_SQL = {
    'binary': """CREATE TABLE IF NOT EXISTS binary (
        id INTEGER PRIMARY KEY,
        repo_path TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        game TEXT,
        platform TEXT,
        variant TEXT,
        language_id TEXT,
        arch TEXT,
        bits INTEGER,
        format TEXT,
        md5 TEXT,
        image_base INTEGER,
        func_count INTEGER,
        named_count INTEGER,
        role TEXT,
        recovery_family TEXT
    )""",
    'func': """CREATE TABLE IF NOT EXISTS func (
        id INTEGER PRIMARY KEY,
        binary_id INTEGER NOT NULL REFERENCES binary(id),
        addr INTEGER NOT NULL,
        name TEXT,
        namespace TEXT,
        source TEXT,
        size INTEGER,
        ranges INTEGER,
        is_thunk INTEGER,
        thunked_to INTEGER,
        calling_convention TEXT,
        return_type TEXT,
        param_count INTEGER,
        param_types TEXT,
        stack_frame_size INTEGER,
        stack_param_size INTEGER,
        stack_local_size INTEGER,
        plate TEXT,
        signature TEXT,
        n_instr INTEGER,
        n_blocks INTEGER,
        n_edges INTEGER,
        back_edges INTEGER,
        cyclomatic INTEGER,
        n_callees INTEGER,
        indirect_calls INTEGER,
        data_refs INTEGER,
        mnem TEXT,
        strings TEXT,
        consts TEXT,
        ext_calls TEXT,
        block_hashes TEXT,
        canon_class TEXT,
        canon_method TEXT,
        canon_key TEXT,
        canon_arity INTEGER,
        name_origin TEXT,
        source_file TEXT,
        object_file TEXT,
        UNIQUE(binary_id, addr)
    )""",
    'calledge': """CREATE TABLE IF NOT EXISTS calledge (
        binary_id INTEGER NOT NULL,
        caller_addr INTEGER NOT NULL,
        callee_addr INTEGER NOT NULL
    )""",
    'logical_function': """CREATE TABLE IF NOT EXISTS logical_function (
        id INTEGER PRIMARY KEY,
        canon_key TEXT,
        canon_class TEXT,
        canon_method TEXT,
        game TEXT,
        best_name TEXT,
        best_signature TEXT,
        source_file TEXT,
        object_file TEXT,
        n_members INTEGER,
        notes TEXT
    )""",
    'identity': """CREATE TABLE IF NOT EXISTS identity (
        logical_id INTEGER NOT NULL REFERENCES logical_function(id),
        binary_id INTEGER NOT NULL,
        addr INTEGER NOT NULL,
        confidence REAL,
        method TEXT,
        evidence TEXT,
        PRIMARY KEY (binary_id, addr)
    )""",
    'stabs_type': """CREATE TABLE IF NOT EXISTS stabs_type (
        id INTEGER PRIMARY KEY,
        binary_id INTEGER NOT NULL,
        source_file TEXT,
        object_file TEXT,
        name TEXT NOT NULL,
        kind TEXT,
        stab TEXT NOT NULL,
        func_addr INTEGER,
        UNIQUE(binary_id, source_file, name, kind, stab, func_addr)
    )""",
    'match': """CREATE TABLE IF NOT EXISTS match (
        id INTEGER PRIMARY KEY,
        run TEXT,
        src_binary INTEGER,
        src_addr INTEGER,
        dst_binary INTEGER,
        dst_addr INTEGER,
        score REAL,
        margin REAL,
        evidence TEXT,
        status TEXT,
        relation TEXT NOT NULL DEFAULT 'one_to_one',
        src_end INTEGER,
        dst_end INTEGER
    )""",
    'eval': """CREATE TABLE IF NOT EXISTS eval (
        run TEXT,
        metric TEXT,
        value REAL,
        detail TEXT
    )""",
    'schema_migration': """CREATE TABLE IF NOT EXISTS schema_migration (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        basis_hash TEXT
    )""",
    'basis_supersession': """CREATE TABLE IF NOT EXISTS basis_supersession (
        id INTEGER PRIMARY KEY,
        old_basis_hash TEXT NOT NULL,
        new_basis_hash TEXT NOT NULL,
        old_algorithm_version TEXT NOT NULL,
        new_algorithm_version TEXT NOT NULL,
        old_package_basis_json TEXT,
        new_package_basis_json TEXT NOT NULL,
        analyzer_version TEXT NOT NULL,
        reason TEXT,
        binaries_restamped INTEGER NOT NULL,
        receipt_sha256 TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        UNIQUE(old_basis_hash, new_basis_hash)
    )""",
    'func_param': """CREATE TABLE IF NOT EXISTS func_param (
        binary_id INTEGER NOT NULL,
        addr INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        name TEXT,
        type TEXT,
        pieces_json TEXT,
        PRIMARY KEY(binary_id, addr, ordinal),
        FOREIGN KEY(binary_id, addr) REFERENCES func(binary_id, addr) ON DELETE CASCADE
    )""",
    'ghidra_field': """CREATE TABLE IF NOT EXISTS ghidra_field (
        binary_id INTEGER NOT NULL REFERENCES binary(id),
        type_name TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        offset INTEGER NOT NULL,
        size INTEGER NOT NULL,
        name TEXT NOT NULL,
        dt_kind TEXT NOT NULL,
        pointee_type TEXT,
        composite_type TEXT,
        element_type TEXT,
        array_count INTEGER,
        type_json TEXT NOT NULL,
        PRIMARY KEY(binary_id, type_name, ordinal)
    )""",
    'bsim_query': """CREATE TABLE IF NOT EXISTS bsim_query (
        src_binary INTEGER NOT NULL REFERENCES binary(id),
        dst_binary INTEGER NOT NULL REFERENCES binary(id),
        database_id TEXT NOT NULL,
        src_digest TEXT NOT NULL,
        dst_digest TEXT NOT NULL,
        state TEXT NOT NULL,
        reason TEXT NOT NULL,
        PRIMARY KEY(src_binary, dst_binary)
    )""",
    'bsim_hit': """CREATE TABLE IF NOT EXISTS bsim_hit (
        src_binary INTEGER NOT NULL REFERENCES binary(id),
        src_addr INTEGER NOT NULL,
        dst_binary INTEGER NOT NULL REFERENCES binary(id),
        dst_addr INTEGER NOT NULL,
        database_id TEXT NOT NULL,
        similarity REAL NOT NULL,
        significance REAL NOT NULL,
        self_significance REAL,
        PRIMARY KEY(src_binary, src_addr, dst_binary, dst_addr)
    )""",
    'recovered_function': """CREATE TABLE IF NOT EXISTS recovered_function (
        program TEXT NOT NULL,
        binary_id INTEGER,
        addr INTEGER,
        name TEXT NOT NULL,
        size INTEGER,
        convention TEXT,
        machine_code TEXT,
        real_c INTEGER NOT NULL,
        logical_id INTEGER,
        path TEXT NOT NULL,
        evidence TEXT,
        source_sha256 TEXT,
        target_sha256 TEXT,
        semantic_status TEXT,
        semantic_reason TEXT,
        semantic_evidence TEXT,
        PRIMARY KEY (program, name, binary_id, addr, path, source_sha256)
    )""",
    'reuse_candidate': """CREATE TABLE IF NOT EXISTS reuse_candidate (
        src_program TEXT NOT NULL,
        src_name TEXT NOT NULL,
        dst_binary_id INTEGER NOT NULL,
        dst_addr INTEGER NOT NULL,
        dst_name TEXT,
        size INTEGER NOT NULL,
        real_c INTEGER NOT NULL,
        basis TEXT NOT NULL,
        PRIMARY KEY (src_program, src_name, dst_binary_id, dst_addr)
    )""",
    'ghidra_type': """CREATE TABLE IF NOT EXISTS ghidra_type (
        binary_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        size INTEGER,
        definition TEXT NOT NULL,
        n_fields INTEGER,
        PRIMARY KEY (binary_id, name, kind)
    )""",
    'ghidra_type_origin': """CREATE TABLE IF NOT EXISTS ghidra_type_origin (
        binary_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        donor_slug TEXT NOT NULL,
        donor_game TEXT,
        size INTEGER,
        PRIMARY KEY (binary_id, name)
    )""",
    'func_convention_derived': """CREATE TABLE IF NOT EXISTS func_convention_derived (
        binary_id INTEGER NOT NULL,
        addr INTEGER NOT NULL,
        deco_class TEXT NOT NULL,
        stack_bytes INTEGER,
        fastcall_n INTEGER,
        class_source TEXT NOT NULL,
        n_source TEXT NOT NULL,
        PRIMARY KEY (binary_id, addr)
    )""",
    'decomp': """CREATE TABLE IF NOT EXISTS decomp (
        binary_id INTEGER NOT NULL,
        addr INTEGER NOT NULL,
        ok INTEGER,
        n_tokens INTEGER,
        n_lines INTEGER,
        max_nest INTEGER,
        n_calls INTEGER,
        n_locals INTEGER,
        n_deref INTEGER,
        n_index INTEGER,
        n_field INTEGER,
        ctrl TEXT,
        ops TEXT,
        skeleton_hash TEXT,
        ast_fingerprint TEXT,
        PRIMARY KEY (binary_id, addr)
    )""",
    'logical_name': """CREATE TABLE IF NOT EXISTS logical_name (
        logical_id INTEGER PRIMARY KEY,
        name TEXT,
        tier INTEGER,
        tier_name TEXT,
        from_binary_id INTEGER,
        source_file TEXT,
        signature TEXT,
        n_members INTEGER,
        detail TEXT
    )""",
    'binary_content_identity': """CREATE TABLE IF NOT EXISTS binary_content_identity (
        source_path TEXT PRIMARY KEY,
        sha256 TEXT NOT NULL
    )""",
    'program_binding': """CREATE TABLE IF NOT EXISTS program_binding (
        source_path TEXT NOT NULL,
        locator TEXT NOT NULL,
        program TEXT NOT NULL,
        updated REAL NOT NULL,
        PRIMARY KEY(source_path,locator)
    )""",
    'binary_source_alias': """CREATE TABLE IF NOT EXISTS binary_source_alias (
        source_path TEXT PRIMARY KEY,
        binary_slug TEXT NOT NULL,
        sha256 TEXT NOT NULL
    )""",
}

INDEX_SQL = {
    'ix_func_bin': 'CREATE INDEX IF NOT EXISTS ix_func_bin ON func(binary_id)',
    'ix_func_canon': 'CREATE INDEX IF NOT EXISTS ix_func_canon ON func(canon_key)',
    'ix_func_class': 'CREATE INDEX IF NOT EXISTS ix_func_class ON func(canon_class)',
    'ix_func_bin_addr': 'CREATE INDEX IF NOT EXISTS ix_func_bin_addr ON func(binary_id, addr)',
    'ix_func_priority_cover': 'CREATE INDEX IF NOT EXISTS ix_func_priority_cover ON func(binary_id, addr, size, n_instr, name)',
    'ix_edge_caller': 'CREATE INDEX IF NOT EXISTS ix_edge_caller ON calledge(binary_id, caller_addr)',
    'ix_edge_callee': 'CREATE INDEX IF NOT EXISTS ix_edge_callee ON calledge(binary_id, callee_addr)',
    'ix_logical_key': 'CREATE INDEX IF NOT EXISTS ix_logical_key ON logical_function(canon_key)',
    'ix_identity_logical': 'CREATE INDEX IF NOT EXISTS ix_identity_logical ON identity(logical_id)',
    'ux_identity_bin_addr': 'CREATE UNIQUE INDEX IF NOT EXISTS ux_identity_bin_addr ON identity(binary_id, addr)',
    'ix_stabs_type_bin': 'CREATE INDEX IF NOT EXISTS ix_stabs_type_bin ON stabs_type(binary_id, kind)',
    'ix_stabs_type_src': 'CREATE INDEX IF NOT EXISTS ix_stabs_type_src ON stabs_type(binary_id, source_file)',
    'ix_match_src': 'CREATE INDEX IF NOT EXISTS ix_match_src ON match(run, src_binary, src_addr)',
    'ix_match_dst': 'CREATE INDEX IF NOT EXISTS ix_match_dst ON match(run, dst_binary, dst_addr)',
    'ix_match_status_score': 'CREATE INDEX IF NOT EXISTS ix_match_status_score ON match(status, score, id)',
    'ix_basis_supersession_new': 'CREATE INDEX IF NOT EXISTS ix_basis_supersession_new ON basis_supersession(new_basis_hash)',
    'ix_bsim_pair': 'CREATE INDEX IF NOT EXISTS ix_bsim_pair ON bsim_hit(src_binary,dst_binary)',
    'ix_match_algorithm_confidence': 'CREATE INDEX IF NOT EXISTS ix_match_algorithm_confidence ON match(algorithm,confidence)',
    'ix_recovered_logical': 'CREATE INDEX IF NOT EXISTS ix_recovered_logical ON recovered_function(logical_id)',
    'ix_reuse_dst': 'CREATE INDEX IF NOT EXISTS ix_reuse_dst ON reuse_candidate(dst_binary_id, dst_addr)',
    'ix_ghidra_type_bin': 'CREATE INDEX IF NOT EXISTS ix_ghidra_type_bin ON ghidra_type(binary_id)',
    'ix_decomp_bin': 'CREATE INDEX IF NOT EXISTS ix_decomp_bin ON decomp(binary_id)',
}

TABLE_SQL.update(match_review_schema.TABLE_SQL)
INDEX_SQL.update(match_review_schema.INDEX_SQL)
INDEX_SQL['ix_func_srcfile'] = 'CREATE INDEX IF NOT EXISTS ix_func_srcfile ON func(binary_id, source_file)'

OPTIONAL_TABLES = frozenset({
    'decomp', 'ghidra_type', 'ghidra_type_origin', 'func_convention_derived',
    'recovered_function', 'reuse_candidate', 'binary_source_alias', 'logical_name',
    'binary_content_identity', 'program_binding',
})
MANDATORY_TABLES = frozenset(TABLE_SQL) - OPTIONAL_TABLES
# Migration additions are required at v9. Writer-only additions remain optional.
REQUIRED_ADDITIONS = {
    'binary': ('content_sha256 TEXT', 'basis_hash TEXT', 'decoder_revision TEXT',
               'analyzer_version TEXT', 'processor_spec_hash TEXT', 'basis_source TEXT'),
    'func': ('cfg_nodes TEXT', 'cfg_edges TEXT', 'hash_reloc TEXT', 'hash_instr TEXT',
             'hash_mnemonic TEXT', 'hash_raw TEXT', 'symbol_provenance TEXT',
             'return_storage TEXT', 'function_properties TEXT'),
    'match': ('kind TEXT', 'confidence REAL', 'algorithm TEXT'),
}
OPTIONAL_ADDITIONS = {
    'binary': ('code_func_count INTEGER',),
    'func': ('stabs_name TEXT', 'stabs_type TEXT'),
    'ghidra_type': ('origin TEXT',),
    'decomp': ('ast_fingerprint TEXT',),
}
LEDGER = tuple(enumerate((
    'baseline', 'analyzer_identity', 'basis_supersession', 'match_review',
    'function_storage', 'typed_fields', 'matching_evidence', 'pcode_channel',
    'match_metadata',
), 1))

# Frozen compatibility deltas: future migration registry edits grant no deletion
# permission. Version 9 retains optional STABS attribution exactly as reviewed.
LEDGER_V10 = LEDGER + ((10, 'stabs_schema_ownership'),)
VERSION_PROFILES = {
    9: (LEDGER, (), frozenset()),
    10: (LEDGER_V10, ('stabs_name TEXT', 'stabs_type TEXT'),
         frozenset({'ix_func_srcfile', 'ix_stabs_type_bin', 'ix_stabs_type_src'})),
}


def open_for_delete(path: pathlib.Path | str) -> sqlite3.Connection:
    """Open an existing store without DDL, backfill, journal changes or mkdir."""
    con = sqlite3.connect(pathlib.Path(path).resolve().as_uri() + '?mode=rw',
                          uri=True, timeout=30)
    try:
        con.row_factory = sqlite3.Row
    except BaseException:
        con.close()
        raise
    return con


# A deliberately small lexer: only source-declared SQLite DDL is admitted. Keep
# string tokens intact (including case/spacing) and refuse comments/expressions
# not present in the allowlist. In particular do not strip whitespace in strings.
_TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|<>|>=|<=|[(),;=+*.<>-]")


def _tokens(sql: str, name: str) -> tuple[str, ...]:
    out = []
    end = 0
    for match in _TOKEN.finditer(sql):
        if sql[end:match.start()].strip():
            raise BinaryDeleteUnsupported('schema_unsupported', name)
        token = match[0]
        out.append(token if token.startswith("'") else token.lower())
        end = match.end()
    if sql[end:].strip():
        raise BinaryDeleteUnsupported('schema_unsupported', name)
    if out[-1:] == [';']:
        out.pop()
    # SQLite omits this clause in sqlite_schema.
    if out[2:5] == ['if', 'not', 'exists']:
        del out[2:5]
    elif out[3:6] == ['if', 'not', 'exists']:
        del out[3:6]
    return tuple(out)


def _clauses(sql: str, name: str) -> frozenset[tuple[str, ...]]:
    tokens = _tokens(sql, name)
    # SQLite's table-rename path quotes only the rebuilt table identifier.
    if tokens[2:3] == ('"' + name + '"',):
        tokens = tokens[:2] + (name,) + tokens[3:]
    if tokens[:4] != ('create', 'table', name, '(') or tokens[-1:] != (')',):
        raise BinaryDeleteUnsupported('schema_unsupported', name)
    clauses = []
    start, depth = 4, 0
    for pos in range(4, len(tokens) - 1):
        token = tokens[pos]
        depth += (token == '(') - (token == ')')
        if depth < 0:
            raise BinaryDeleteUnsupported('schema_unsupported', name)
        if token == ',' and depth == 0:
            clauses.append(tokens[start:pos])
            start = pos + 1
    clauses.append(tokens[start:-1])
    if depth or any(not clause for clause in clauses) or len(set(clauses)) != len(clauses):
        raise BinaryDeleteUnsupported('schema_unsupported', name)
    return frozenset(clauses)


def _schema_preflight(con: sqlite3.Connection) -> frozenset[str]:
    for row in con.execute('PRAGMA database_list'):
        if row[1] not in {'main', 'temp'}:
            raise BinaryDeleteUnsupported('schema_unsupported', 'attached.' + row[1])
    if con.execute('SELECT 1 FROM temp.sqlite_schema LIMIT 1').fetchone():
        raise BinaryDeleteUnsupported('schema_unsupported', 'temp')
    version = con.execute('PRAGMA main.user_version').fetchone()[0]
    if version not in VERSION_PROFILES:
        raise BinaryDeleteUnsupported('schema_unsupported', 'user_version')
    expected_ledger, func_additions, required_indexes = VERSION_PROFILES[version]
    objects = list(con.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema'))
    missing_indexes = required_indexes - {row[1] for row in objects if row[0] == 'index'}
    if missing_indexes:
        raise BinaryDeleteUnsupported('schema_unsupported', sorted(missing_indexes)[0])
    present = frozenset(row[1] for row in objects if row[0] == 'table' and row[1] in TABLE_SQL)
    missing = MANDATORY_TABLES - present
    if missing:
        raise BinaryDeleteUnsupported('schema_unsupported', sorted(missing)[0])
    for kind, name, table, sql in objects:
        if name in {'sqlite_sequence', 'sqlite_stat1', 'sqlite_stat4'} and kind == 'table':
            continue
        if kind == 'table' and name in TABLE_SQL:
            actual = _clauses(sql, name)
            required = set(_clauses(TABLE_SQL[name], name))
            required.update(_tokens(item, name) for item in REQUIRED_ADDITIONS.get(name, ()))
            optional = {_tokens(item, name) for item in OPTIONAL_ADDITIONS.get(name, ())}
            required -= optional
            if name == 'func':
                required.update(_tokens(item, name) for item in func_additions)
            if not required <= actual or not actual <= required | optional:
                raise BinaryDeleteUnsupported('schema_unsupported', name)
        elif kind == 'index':
            if sql is None and name.startswith('sqlite_autoindex_') and table in present:
                continue  # Engine-generated keys follow the validated table DDL.
            if name not in INDEX_SQL or not sql or _tokens(sql, name) != _tokens(INDEX_SQL[name], name):
                raise BinaryDeleteUnsupported('schema_unsupported', name)
        elif kind == 'trigger':
            expected = match_review_schema.TRIGGER_SQL.get(name)
            if expected is None or not sql or match_review_schema._normalized(sql) != match_review_schema._normalized(expected):
                raise BinaryDeleteUnsupported('schema_unsupported', name)
        else:
            raise BinaryDeleteUnsupported('schema_unsupported', name)
    for child, parent in (('reuse_candidate', 'recovered_function'), ('ghidra_type_origin', 'ghidra_type')):
        if child in present and parent not in present:
            raise BinaryDeleteUnsupported('schema_unsupported', parent)
    ledger = tuple(tuple(row) for row in con.execute(
        'SELECT version,name FROM main.schema_migration ORDER BY version'))
    if ledger != expected_ledger:
        raise BinaryDeleteUnsupported('schema_unsupported', 'schema_migration')
    try:
        match_review_schema.require(con)
    except ValueError as exc:
        raise BinaryDeleteUnsupported('schema_unsupported', 'match_review') from exc
    return present


@dataclass(frozen=True)
class DeleteRule:
    table: str
    predicate: str
    parameters: tuple[object, ...]


DELETE_ORDER = (
    'reuse_candidate', 'recovered_function', 'logical_name', 'bsim_hit',
    'bsim_query', 'match', 'calledge', 'func_param', 'func_convention_derived',
    'decomp', 'ghidra_field', 'ghidra_type_origin', 'ghidra_type', 'stabs_type',
    'identity', 'func', 'binary_source_alias', 'binary',
)


def _plan(present: frozenset[str], bid: int, slug: str) -> list[DeleteRule]:
    rules = []
    for table in DELETE_ORDER:
        if table not in present:
            continue
        if table == 'reuse_candidate':
            rules.append(DeleteRule(table, 'dst_binary_id=?', (bid,)))
            # Second pass excludes first-pass rows in its pre-write count. The
            # survivor predicate must retain NULL/unbound recovered candidates.
            predicate = '''dst_binary_id<>? AND EXISTS (
                SELECT 1 FROM main.recovered_function AS removed
                WHERE removed.binary_id=? AND removed.program=reuse_candidate.src_program
                AND removed.name=reuse_candidate.src_name)
                AND NOT EXISTS (SELECT 1 FROM main.recovered_function AS survivor
                WHERE (survivor.binary_id<>? OR survivor.binary_id IS NULL)
                AND survivor.program=reuse_candidate.src_program
                AND survivor.name=reuse_candidate.src_name)'''
            rules.append(DeleteRule(table, predicate, (bid, bid, bid)))
        elif table == 'logical_name':
            rules.append(DeleteRule(table, '''from_binary_id=? OR logical_id IN
                (SELECT logical_id FROM main.identity WHERE binary_id=?)''', (bid, bid)))
        elif table in {'bsim_hit', 'bsim_query', 'match'}:
            rules.append(DeleteRule(table, 'src_binary=? OR dst_binary=?', (bid, bid)))
        elif table == 'binary_source_alias':
            rules.append(DeleteRule(table, 'binary_slug=?', (slug,)))
        elif table == 'binary':
            rules.append(DeleteRule(table, 'id=?', (bid,)))
        else:
            rules.append(DeleteRule(table, 'binary_id=?', (bid,)))
    return rules


def _dependency_preflight(con: sqlite3.Connection, present: frozenset[str], bid: int) -> None:
    gates = (
        ('identity', 'binary_id IS NOT ?', (bid,)),
        ('match', '(src_binary IS NOT ? AND dst_binary IS NOT ?)', (bid, bid)),
        ('recovered_function', 'binary_id IS NOT ? AND logical_id IS NOT NULL', (bid,)),
        ('func_convention_derived', 'binary_id IS NOT ?', (bid,)),
    )
    for table, predicate, params in gates:
        if table in present and con.execute(
            f'SELECT 1 FROM main.{table} WHERE {predicate} LIMIT 1', params
        ).fetchone():
            raise BinaryDeleteUnsupported('dependency_unsupported', table)


def _owner_preflight(con: sqlite3.Connection, present: frozenset[str]) -> None:
    # Inspect storage, not CAST/int coercions. All live binary owners must resolve;
    # NULL recovered owners are explicitly independent, preserved source records.
    owners = {table: ('binary_id',) for table in (
        'func', 'calledge', 'identity', 'stabs_type', 'func_param', 'ghidra_field',
        'decomp', 'ghidra_type', 'ghidra_type_origin', 'func_convention_derived',
        'recovered_function',
    )}
    owners.update({table: ('src_binary', 'dst_binary') for table in ('match', 'bsim_hit', 'bsim_query')})
    owners['reuse_candidate'] = ('dst_binary_id',)
    for table, columns in owners.items():
        if table not in present:
            continue
        for column in columns:
            nullable = table == 'recovered_function'
            predicate = f"(typeof({column})<>'integer' OR NOT EXISTS (SELECT 1 FROM main.binary AS b WHERE b.id={table}.{column}))"
            if nullable:
                predicate = f'{column} IS NOT NULL AND {predicate}'
            if con.execute(f'SELECT 1 FROM main.{table} WHERE {predicate} LIMIT 1').fetchone():
                reason = 'dependency_unsupported' if table in {'identity', 'match', 'func_convention_derived'} else 'owner_unsupported'
                raise BinaryDeleteUnsupported(reason, table)
    if con.execute('''SELECT 1 FROM main.identity AS i WHERE typeof(logical_id)<>'integer'
        OR NOT EXISTS (SELECT 1 FROM main.logical_function AS l WHERE l.id=i.logical_id) LIMIT 1''').fetchone():
        raise BinaryDeleteUnsupported('owner_unsupported', 'identity.logical_id')
    # Composite keys in SQLite rowid tables can hold NULL despite being a PK.
    # Honor declared nullability while refusing non-integral address/key storage.
    for table in sorted(present):
        for _, column, declared, notnull, _, pk in con.execute(f'PRAGMA main.table_info({table})'):
            if not pk and column not in {'addr', 'caller_addr', 'callee_addr', 'src_addr', 'dst_addr', 'logical_id'}:
                continue
            expected_type = {'INTEGER': 'integer', 'TEXT': 'text'}.get(declared.upper())
            if expected_type is None:
                continue
            predicate = f"typeof({column})<>?"
            if not notnull:
                predicate = f'{column} IS NOT NULL AND ({predicate})'
            if con.execute(f'SELECT 1 FROM main.{table} WHERE {predicate} LIMIT 1', (expected_type,)).fetchone():
                raise BinaryDeleteUnsupported('owner_unsupported', table + '.' + column)
    if con.execute("SELECT 1 FROM main.binary WHERE typeof(slug)<>'text' OR typeof(repo_path)<>'text' LIMIT 1").fetchone():
        raise BinaryDeleteUnsupported('owner_unsupported', 'binary')
    if 'binary_source_alias' in present and con.execute('''SELECT 1 FROM main.binary_source_alias
        WHERE typeof(binary_slug)<>'text' OR NOT EXISTS
        (SELECT 1 FROM main.binary WHERE slug=binary_source_alias.binary_slug) LIMIT 1''').fetchone():
        raise BinaryDeleteUnsupported('owner_unsupported', 'binary_source_alias')
    if 'logical_name' in present and con.execute('''SELECT 1 FROM main.logical_name
        WHERE from_binary_id IS NOT NULL AND typeof(from_binary_id)<>'integer' LIMIT 1''').fetchone():
        raise BinaryDeleteUnsupported('owner_unsupported', 'logical_name')


def _count(con: sqlite3.Connection, rule: DeleteRule) -> int:
    return con.execute(f'SELECT COUNT(*) FROM main.{rule.table} WHERE {rule.predicate}', rule.parameters).fetchone()[0]


def _revision_preflight(con: sqlite3.Connection, keys: list[tuple[str, int]]) -> None:
    for kind, entity in keys:
        row = con.execute('''SELECT revision,typeof(revision),binary_repo_path,binary_slug
            FROM main.match_review_revision WHERE kind=? AND entity_id=?''', (kind, entity)).fetchone()
        clock = con.execute('SELECT next_revision FROM main.match_review_control WHERE singleton=1').fetchone()[0]
        if row is None or row[1] != 'integer' or not 0 < row[0] <= clock:
            raise BinaryDeleteUnsupported('schema_unsupported', 'match_review_revision')
        expected_keys = (None, None)
        if kind == 'binary':
            expected_keys = tuple(con.execute(
                'SELECT repo_path,slug FROM main.binary WHERE id=?', (entity,)).fetchone())
        if tuple(row[2:]) != expected_keys:
            raise BinaryDeleteUnsupported('schema_unsupported', 'match_review_revision')


def remove_binary(con: sqlite3.Connection, *, repo_path: str | None = None, slug: str | None = None) -> dict:
    """Remove one admitted binary atomically; caller-owned success is provisional.

    Release only our savepoint when the caller owns a transaction. The returned
    receipt becomes durable only when that caller commits. Never close *con*.
    """
    if not repo_path and not slug:
        raise ValueError('repo_path or slug is required')
    owned = not con.in_transaction
    savepoint = 'binary_delete_' + uuid.uuid4().hex
    # BEGIN/SAVEPOINT failure precedes our scope, so do not roll back caller work.
    con.execute('BEGIN IMMEDIATE' if owned else f'SAVEPOINT {savepoint}')
    try:
        present = _schema_preflight(con)
        selector = 'repo_path' if repo_path else 'slug'
        rows = con.execute(f'SELECT id,slug,repo_path FROM main.binary WHERE {selector}=?',
                           (repo_path or slug,)).fetchall()
        if not rows:
            raise SystemExit(f'no binary matching {repo_path or slug!r}')
        if len(rows) != 1 or type(rows[0][0]) is not int:
            raise BinaryDeleteUnsupported('owner_unsupported', 'binary')
        bid, stored_slug, stored_path = rows[0]
        _dependency_preflight(con, present, bid)
        _owner_preflight(con, present)
        logical_ids = [row[0] for row in con.execute(
            'SELECT DISTINCT logical_id FROM main.identity WHERE binary_id=? ORDER BY logical_id', (bid,))]
        revision_keys = [('binary', bid)] + [('match', row[0]) for row in con.execute(
            'SELECT id FROM main.match WHERE src_binary=? OR dst_binary=? ORDER BY id', (bid, bid))]
        _revision_preflight(con, revision_keys)
        rules = _plan(present, bid, stored_slug)
        intended = [_count(con, rule) for rule in rules]
        if intended[-1] != 1:
            raise BinaryDeleteUnsupported('count_mismatch', 'binary')
        deleted = dict.fromkeys(DELETE_ORDER, 0)
        # All query/schema/dependency validation above precedes the first write.
        for rule, expected in zip(rules, intended):
            if rule.table == 'binary':
                for logical_id in logical_ids:
                    cur = con.execute('''UPDATE main.logical_function SET n_members=
                        (SELECT COUNT(*) FROM main.identity WHERE logical_id=?) WHERE id=?''',
                        (logical_id, logical_id))
                    if cur.rowcount != 1:
                        raise BinaryDeleteUnsupported('count_mismatch', 'logical_function')
            actual = con.execute(f'DELETE FROM main.{rule.table} WHERE {rule.predicate}', rule.parameters).rowcount
            if actual != expected or _count(con, rule) != 0:
                raise BinaryDeleteUnsupported('count_mismatch', rule.table)
            deleted[rule.table] += actual
        for kind, entity in revision_keys:
            if con.execute('SELECT 1 FROM main.match_review_revision WHERE kind=? AND entity_id=?', (kind, entity)).fetchone():
                raise BinaryDeleteUnsupported('count_mismatch', 'match_review_revision')
        for logical_id in logical_ids:
            row = con.execute('''SELECT n_members,(SELECT COUNT(*) FROM main.identity WHERE logical_id=?)
                FROM main.logical_function WHERE id=?''', (logical_id, logical_id)).fetchone()
            if row is None or row[0] != row[1]:
                raise BinaryDeleteUnsupported('count_mismatch', 'logical_function')
        deleted.update(match_review_revision=len(revision_keys), logical_function=0, match_review_audit=0)
        if owned:
            con.commit()
        else:
            con.execute(f'RELEASE SAVEPOINT {savepoint}')
    except BaseException:
        # Rollback errors are deliberately surfaced (chained to the original),
        # including an outer transaction invalidated by SQLite itself.
        if owned:
            con.rollback()
        else:
            con.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
            con.execute(f'RELEASE SAVEPOINT {savepoint}')
        raise
    return {'id': bid, 'slug': stored_slug, 'repo_path': stored_path, 'deleted': deleted}
