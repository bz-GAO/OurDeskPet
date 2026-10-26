"""Opt-in, local terminology packs. No model calls or source-text rewriting."""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def _read(path):
    if path.stat().st_size > 512_000:
        raise ValueError(f'术语文件过大：{path.name}')
    raw = path.read_bytes()
    return json.loads(raw.decode('utf-8-sig')), raw


@dataclass
class Pack:
    directory: Path
    manifest: dict

    @property
    def id(self):
        return self.manifest['pack_id']

    @property
    def draft(self):
        return self.manifest.get('runtime_enabled') is not True or self.manifest.get('status','').startswith('draft')

    def compatible(self, source, target):
        return (source,target) == (self.manifest['source_language'],self.manifest['target_language'])


def discover_packs(root):
    packs, errors = [], []
    directory = (Path(root)/'translation_guidance/packs').resolve()
    for path in sorted(directory.glob('*/pack.json')):
        try:
            if not path.resolve().is_relative_to(directory):
                raise ValueError('包路径越界')
            data, _ = _read(path)
            for key in ('pack_id','name','version','source_language','target_language'):
                if not isinstance(data.get(key),str) or not data[key].strip():
                    raise ValueError(f'缺少 {key}')
            if data.get('schema_version') != 1 or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}',data['pack_id']):
                raise ValueError('不支持的清单版本或包 ID')
            hint = data.get('domain_hint', '')
            if not isinstance(hint, str) or len(hint.split()) > 80 or any(ord(ch) > 127 or ord(ch) < 32 for ch in hint):
                raise ValueError('领域提示必须是 80 词以内的英文短句')
            packs.append(Pack(path.parent,data))
        except (OSError,ValueError,TypeError,AttributeError) as error:
            errors.append(f'{path.parent.name}：{error}')
    duplicates = {pack.id for pack in packs if sum(other.id==pack.id for other in packs)>1}
    errors.extend(f'重复包 ID，已禁用：{name}' for name in sorted(duplicates))
    return [pack for pack in packs if pack.id not in duplicates], errors


@dataclass(frozen=True)
class Term:
    source: str
    target: str
    entity: str
    pack_id: str
    needs_context: bool
    pattern: object


class Guidance:
    def __init__(self, terms=(), provenance=(), domain_hints=()):
        self.terms = tuple(terms)
        self.provenance = list(provenance)
        hints, word_count = [], 0
        for hint in dict.fromkeys(domain_hints):
            count = len(hint.split())
            if word_count + count > 120:
                break
            hints.append(hint)
            word_count += count
        self.domain_hint = ' '.join(hints)
        self._recent = deque(maxlen=2)

    def match(self,text):
        normalized = unicodedata.normalize('NFKC',text)
        hits = [(term,match) for term in self.terms for match in term.pattern.finditer(normalized)]
        targets = {}
        for term,match in hits:
            targets.setdefault(match.group(),set()).add(term.target)
        current = {term.entity for term,match in hits if not term.needs_context and len(targets[match.group()])==1}
        known = current.union(*(self._recent or [set()]))
        self._recent.append(current)
        # Longest match wins, then source order. Conflicting targets are omitted,
        # never arbitrarily resolved by pack/file order.
        hits.sort(key=lambda item:(-(item[1].end()-item[1].start()),item[1].start()))
        occupied, result, seen = [], [], set()
        for term,match in hits:
            if term.needs_context:
                context = term.entity in known
                if ':term.' in term.entity:
                    context = any(entity.startswith(term.pack_id+':') for entity in known)
                if not context or len(term.source)<2:
                    continue
            start,end = match.span()
            if any(start<b and end>a for a,b in occupied):
                continue
            occupied.append((start,end))
            if len(targets[match.group()]) != 1 or match.group() in seen:
                continue
            seen.add(match.group())
            result.append({'source':match.group(),'target':term.target})
            if len(result)>=12:
                break
        return result

    def static_phrases(self, limit=80):
        """Unambiguous names for a live model that cannot wait for text context."""
        targets = {}
        for term in self.terms:
            if not term.needs_context:
                targets.setdefault(term.source, set()).add(term.target)
        phrases = {}
        for source, values in targets.items():
            if len(values) == 1:
                phrases[source] = next(iter(values))
            if len(phrases) >= limit:
                break
        return phrases


def load_guidance(root, selected, source, target, *, allow_draft=False):
    if not selected:
        return Guidance()
    packs, _ = discover_packs(root)
    by_id = {pack.id:pack for pack in packs}
    terms, provenance, domain_hints = [], [], []
    for pack_id in dict.fromkeys(selected):
        if pack_id not in by_id:
            raise ValueError(f'术语包不存在或清单无效：{pack_id}')
        pack = by_id[pack_id]
        if not pack.compatible(source,target):
            raise ValueError(f'术语包语言方向不匹配：{pack_id}')
        if pack.draft and not allow_draft:
            raise ValueError(f'术语包尚属草案，需明确选择试用：{pack_id}')
        if pack.manifest.get('domain_hint'):
            domain_hints.append(pack.manifest['domain_hint'].strip())
        files = pack.manifest.get('data_files')
        if not isinstance(files,list) or not 1<=len(files)<=16 or not all(isinstance(x,str) for x in files):
            raise ValueError(f'术语数据清单无效：{pack_id}')
        digest = hashlib.sha256(json.dumps(pack.manifest,sort_keys=True,ensure_ascii=False).encode())
        ids = set()
        for name in files:
            if name in pack.manifest.get('review_files',[]) or name in ('nickname-candidates.json','honorific-policy.json'):
                raise ValueError('待审文件不得列入 data_files')
            path = (pack.directory/name).resolve()
            if not path.is_relative_to(pack.directory.resolve()) or path.suffix!='.json':
                raise ValueError('术语文件路径无效')
            entries, raw = _read(path)
            digest.update(raw)
            if not isinstance(entries,list) or len(entries)>2000:
                raise ValueError('术语条目格式或数量无效')
            for entry in entries:
                if not isinstance(entry,dict) or not isinstance(entry.get('id'),str) or entry['id'] in ids:
                    raise ValueError('术语实体 ID 缺失或重复')
                ids.add(entry['id'])
                if entry.get('enabled') is False or entry.get('status')=='needs_review':
                    continue
                aliases = entry.get('aliases',[])
                if not isinstance(aliases,list) or len(aliases)>100:
                    raise ValueError('别名格式或数量无效')
                for pair in [entry,*aliases]:
                    if not isinstance(pair,dict):
                        raise ValueError('术语对格式无效')
                    if pair.get('enabled') is False or pair.get('status')=='needs_review':
                        continue
                    src,dst = pair.get('source'),pair.get('target')
                    if not all(isinstance(x,str) and x.strip() and len(x)<=160 for x in (src,dst)):
                        raise ValueError('术语对必须是非空短文本')
                    mode = pair.get('match')
                    if mode not in ('exact_name','context_required'):
                        raise ValueError('不支持的术语匹配策略')
                    src = unicodedata.normalize('NFKC',src)
                    pieces = list(''.join(src.split())) if any(not ch.isascii() for ch in src) else src.split()
                    pattern = r'\s*'.join(re.escape(piece) for piece in pieces)
                    if src[0].isascii() and src[0].isalnum():
                        pattern = r'(?<![A-Za-z0-9_])'+pattern
                    if src[-1].isascii() and src[-1].isalnum():
                        pattern += r'(?![A-Za-z0-9_])'
                    terms.append(Term(src,dst,pack_id+':'+entry['id'],pack_id,mode=='context_required',re.compile(pattern)))
                    if len(terms)>10000:
                        raise ValueError('选中术语过多，请减少启用的术语包')
        provenance.append({'pack_id':pack.id,'name':pack.manifest['name'],'version':pack.manifest['version'],
                           'sha256':digest.hexdigest(),'draft_trial':pack.draft})
    return Guidance(terms,provenance,domain_hints)
