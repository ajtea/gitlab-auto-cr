#!/usr/bin/env python3
"""
AI Code Review pro GitLab MR
Analyzuje změny v Merge Requestu a přidává inline komentáře.
Podporuje: OpenAI (ChatGPT) i Anthropic (Claude)

Docker usage:
  docker run -e GITLAB_TOKEN=... -e OPENAI_API_KEY=... ai-code-review
"""

import os
import json
import sys
import requests
from pathlib import Path

# === Konfigurace z ENV ===
GITLAB_URL = os.environ.get("CI_SERVER_URL", "https://gitlab.com")
PROJECT_ID = os.environ.get("CI_PROJECT_ID")
MR_IID = os.environ.get("CI_MERGE_REQUEST_IID")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")

# AI Provider
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AI_PROVIDER = os.environ.get("AI_PROVIDER", "auto")

# Modely
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# Pravidla - priorita: 
# 1. REVIEW_RULES_CONTENT (přímo obsah)
# 2. REVIEW_RULES_FILE (cesta k souboru)
# 3. Soubor v projektu (pokud existuje CI_PROJECT_DIR)
# 4. Default pravidla v image
REVIEW_RULES_FILE = os.environ.get("REVIEW_RULES_FILE", "/app/default_rules.md")
REVIEW_RULES_CONTENT = os.environ.get("REVIEW_RULES_CONTENT", "")

# Konfigurace review
IGNORE_PATTERNS_EXTRA = os.environ.get("IGNORE_PATTERNS", "")  # čárkami oddělené
REVIEW_EXTENSIONS_EXTRA = os.environ.get("REVIEW_EXTENSIONS", "")  # čárkami oddělené
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "50000"))  # max velikost souboru v chars
LANGUAGE = os.environ.get("REVIEW_LANGUAGE", "cs")  # cs / en

# Základní ignorované patterns
IGNORE_PATTERNS = [
    "*.lock", "*.min.js", "*.min.css",
    "package-lock.json", "yarn.lock", "composer.lock", "pnpm-lock.yaml",
    "__pycache__", ".git", "node_modules", "vendor/",
    "*.generated.*", "*.map",
    "storage/", "bootstrap/cache/", "public/build/", "public/hot",
    "dist/", "build/", ".next/", ".nuxt/",
    "_ide_helper*", ".phpstorm.meta.php",
]

# Základní podporované přípony
REVIEW_EXTENSIONS = {
    ".php", ".vue", ".blade.php",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs",
    ".java", ".kt", ".go", ".rs", ".rb",
    ".cs", ".cpp", ".c", ".h", ".swift",
}


def init_config():
    """Inicializuje konfiguraci z ENV proměnných."""
    global IGNORE_PATTERNS, REVIEW_EXTENSIONS
    
    # Přidání extra ignore patterns
    if IGNORE_PATTERNS_EXTRA:
        extra = [p.strip() for p in IGNORE_PATTERNS_EXTRA.split(",") if p.strip()]
        IGNORE_PATTERNS.extend(extra)
    
    # Přidání extra extensions
    if REVIEW_EXTENSIONS_EXTRA:
        extra = [e.strip() if e.strip().startswith(".") else f".{e.strip()}" 
                 for e in REVIEW_EXTENSIONS_EXTRA.split(",") if e.strip()]
        REVIEW_EXTENSIONS.update(extra)


class AIClient:
    """Abstrakce pro různé AI providery (OpenAI, Anthropic)."""
    
    def __init__(self, provider: str = "auto"):
        self.provider = self._detect_provider(provider)
        self._init_client()
    
    def _detect_provider(self, provider: str) -> str:
        if provider != "auto":
            return provider
        if OPENAI_API_KEY:
            return "openai"
        elif ANTHROPIC_API_KEY:
            return "anthropic"
        else:
            raise ValueError("Není nastaven žádný API klíč (OPENAI_API_KEY nebo ANTHROPIC_API_KEY)")
    
    def _init_client(self):
        if self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
            self.model = OPENAI_MODEL
            print(f"🤖 Používám OpenAI ({self.model})")
        else:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
            self.model = ANTHROPIC_MODEL
            print(f"🤖 Používám Anthropic ({self.model})")
    
    def chat(self, prompt: str) -> str:
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()


class GitLabClient:
    """Klient pro komunikaci s GitLab API."""
    
    def __init__(self, base_url: str, token: str, project_id: str):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.headers = {"PRIVATE-TOKEN": token}
    
    def _api(self, endpoint: str) -> str:
        return f"{self.base_url}/api/v4/projects/{self.project_id}/{endpoint}"
    
    def get_mr_changes(self, mr_iid: str) -> dict:
        url = self._api(f"merge_requests/{mr_iid}/changes")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def get_mr_info(self, mr_iid: str) -> dict:
        url = self._api(f"merge_requests/{mr_iid}")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def get_file_content(self, file_path: str, ref: str) -> str | None:
        import urllib.parse
        encoded_path = urllib.parse.quote(file_path, safe="")
        url = self._api(f"repository/files/{encoded_path}/raw?ref={ref}")
        response = requests.get(url, headers=self.headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.text
    
    def create_mr_discussion(
        self, mr_iid: str, body: str, file_path: str, new_line: int,
        base_sha: str, head_sha: str, start_sha: str,
    ):
        url = self._api(f"merge_requests/{mr_iid}/discussions")
        payload = {
            "body": body,
            "position": {
                "position_type": "text",
                "base_sha": base_sha,
                "head_sha": head_sha,
                "start_sha": start_sha,
                "new_path": file_path,
                "new_line": new_line,
            },
        }
        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code >= 400:
            print(f"⚠️  Nepodařilo se vytvořit komentář: {response.text}")
        return response
    
    def create_mr_note(self, mr_iid: str, body: str):
        url = self._api(f"merge_requests/{mr_iid}/notes")
        response = requests.post(url, headers=self.headers, json={"body": body})
        response.raise_for_status()
        return response.json()

    def get_mr_discussions(self, mr_iid: str) -> list:
        """Načte všechny diskuse (inline komentáře) pro MR."""
        url = self._api(f"merge_requests/{mr_iid}/discussions")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_mr_notes(self, mr_iid: str) -> list:
        """Načte všechny notes (komentáře na úrovni MR)."""
        url = self._api(f"merge_requests/{mr_iid}/notes")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def update_mr_note(self, mr_iid: str, note_id: int, body: str):
        """Aktualizuje existující note."""
        url = self._api(f"merge_requests/{mr_iid}/notes/{note_id}")
        response = requests.put(url, headers=self.headers, json={"body": body})
        response.raise_for_status()
        return response.json()

    def resolve_discussion(self, mr_iid: str, discussion_id: str):
        """Označí diskusi jako vyřešenou."""
        url = self._api(f"merge_requests/{mr_iid}/discussions/{discussion_id}")
        response = requests.put(url, headers=self.headers, json={"resolved": True})
        if response.status_code >= 400:
            print(f"⚠️  Nepodařilo se resolvnout diskusi: {response.text}")
        return response

    def delete_mr_note(self, mr_iid: str, note_id: int):
        """Smaže note (komentář) z MR."""
        url = self._api(f"merge_requests/{mr_iid}/notes/{note_id}")
        response = requests.delete(url, headers=self.headers)
        if response.status_code >= 400:
            print(f"⚠️  Nepodařilo se smazat note: {response.text}")
        return response


def should_review_file(file_path: str) -> bool:
    """Rozhodne, zda soubor reviewovat."""
    path = Path(file_path)
    
    for pattern in IGNORE_PATTERNS:
        if pattern.startswith("*"):
            if path.suffix == pattern[1:] or path.name.endswith(pattern[1:]):
                return False
        elif pattern.endswith("/"):
            if pattern[:-1] in file_path:
                return False
        elif pattern in file_path:
            return False
    
    return path.suffix.lower() in REVIEW_EXTENSIONS


def parse_diff_for_new_lines(diff: str) -> list[int]:
    """Parsuje diff a vrací čísla nových/změněných řádků."""
    new_lines = []
    current_new_line = 0
    
    for line in diff.split("\n"):
        if line.startswith("@@"):
            try:
                plus_part = line.split("+")[1].split("@@")[0].strip()
                if "," in plus_part:
                    current_new_line = int(plus_part.split(",")[0])
                else:
                    current_new_line = int(plus_part)
            except (IndexError, ValueError):
                continue
        elif line.startswith("+") and not line.startswith("+++"):
            new_lines.append(current_new_line)
            current_new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass
        elif not line.startswith("\\"):
            current_new_line += 1
    
    return new_lines


def load_review_rules() -> str:
    """Načte pravidla pro review."""
    # 1. Přímo z ENV
    if REVIEW_RULES_CONTENT:
        print("📋 Pravidla načtena z REVIEW_RULES_CONTENT")
        return REVIEW_RULES_CONTENT
    
    # 2. Ze souboru v projektu (pokud existuje)
    project_rules = Path(os.environ.get("CI_PROJECT_DIR", "")) / "review_rules.md"
    if project_rules.exists():
        print(f"📋 Pravidla načtena z projektu: {project_rules}")
        return project_rules.read_text()
    
    # 3. Z REVIEW_RULES_FILE
    rules_file = Path(REVIEW_RULES_FILE)
    if rules_file.exists():
        print(f"📋 Pravidla načtena z: {rules_file}")
        return rules_file.read_text()
    
    # 4. Fallback
    print("📋 Používám výchozí pravidla")
    return "Základní pravidla: SOLID, Clean Code, DRY, bezpečnost."


def detect_file_type(file_path: str) -> str:
    """Detekuje typ souboru pro lepší kontext."""
    if file_path.endswith(".php"):
        if "/Controllers/" in file_path:
            return "Laravel Controller"
        elif "/Models/" in file_path:
            return "Laravel Model"
        elif "/Services/" in file_path:
            return "Laravel Service"
        elif "/Requests/" in file_path:
            return "Laravel Form Request"
        elif "/Resources/" in file_path:
            return "Laravel Resource"
        elif "/Actions/" in file_path:
            return "Laravel Action"
        elif "/Jobs/" in file_path:
            return "Laravel Job"
        elif "/Events/" in file_path:
            return "Laravel Event"
        elif "/Listeners/" in file_path:
            return "Laravel Listener"
        return "PHP/Laravel"
    elif file_path.endswith(".vue"):
        return "Vue/Inertia komponenta"
    elif file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
        if "/composables/" in file_path.lower() or "/use" in file_path.lower():
            return "Vue Composable"
        elif "/components/" in file_path.lower():
            return "Frontend komponenta"
        return "JavaScript/TypeScript"
    elif file_path.endswith(".py"):
        return "Python"
    elif file_path.endswith(".go"):
        return "Go"
    return "Zdrojový kód"


def get_language_prompt(lang: str) -> tuple[str, str]:
    """Vrací jazykově specifické části promptu."""
    if lang == "en":
        return (
            "You are an experienced senior developer performing code review.",
            "brief but clear comment (in English)",
        )
    return (
        "Jsi zkušený senior vývojář provádějící code review.",
        "stručný, ale srozumitelný komentář (česky)",
    )


def analyze_with_ai(
    ai_client: AIClient,
    file_path: str,
    file_content: str,
    diff: str,
    changed_lines: list[int],
    rules: str,
) -> list[dict]:
    """Analyzuje kód pomocí AI a vrací seznam komentářů."""
    
    file_type = detect_file_type(file_path)
    intro, comment_lang = get_language_prompt(LANGUAGE)
    
    prompt = f"""{intro}

## Pravidla a principy, které kontroluješ:
{rules}

## Analyzovaný soubor: {file_path}
## Typ souboru: {file_type}

Aplikuj pravidla relevantní pro tento typ souboru.

### Celý obsah souboru (pro kontext):
```
{file_content[:MAX_FILE_SIZE]}
```

### Diff (změny v tomto MR):
```diff
{diff}
```

### Řádky, které byly změněny/přidány: {changed_lines}

## Tvůj úkol:
1. Analyzuj POUZE změněné řádky (ne celý soubor)
2. Hledej problémy s architekturou, designem, čitelností, principy SOLID, DRY atd.
3. NEKOMENTUJ drobnosti jako chybějící mezery nebo formátování (to řeší linter)
4. Komentuj pouze DŮLEŽITÉ problémy, které stojí za pozornost

## Formát odpovědi:
Vrať POUZE validní JSON pole. Každý objekt má:
- "line": číslo řádku (musí být z {changed_lines})
- "severity": "critical" | "warning" | "suggestion"  
- "message": {comment_lang}
- "suggestion": volitelně - návrh jak to udělat lépe

Pokud není co komentovat, vrať prázdné pole: []

POUZE JSON, žádný další text před ani po:"""

    response_text = ai_client.chat(prompt)
    
    try:
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        comments = json.loads(response_text)
        valid_comments = [
            c for c in comments 
            if isinstance(c, dict) 
            and c.get("line") in changed_lines
            and c.get("message")
        ]
        return valid_comments
        
    except json.JSONDecodeError as e:
        print(f"⚠️  Nepodařilo se parsovat odpověď: {e}")
        print(f"Odpověď: {response_text[:500]}")
        return []


def format_comment(comment: dict) -> str:
    """Formátuje komentář pro GitLab."""
    severity_emoji = {
        "critical": "🔴",
        "warning": "🟡", 
        "suggestion": "💡",
    }
    
    emoji = severity_emoji.get(comment.get("severity", "suggestion"), "💬")
    message = comment.get("message", "")
    suggestion = comment.get("suggestion", "")
    
    text = f"{emoji} **RejPAL**: {message}"
    if suggestion:
        text += f"\n\n> 💡 **Návrh**: {suggestion}"

    return text


def find_existing_summary_note(notes: list) -> int | None:
    """Najde ID existujícího AI sumáře, pokud existuje."""
    for note in notes:
        body = note.get("body", "")
        # Zpětná kompatibilita - hledáme staré i nové názvy
        if "## RejPAL" in body or "## 🤖 AI Code Review" in body:
            return note.get("id")
    return None


def get_existing_ai_comments(discussions: list) -> list[dict]:
    """Vrátí seznam AI Review komentářů s jejich ID pro mazání."""
    existing = []
    for discussion in discussions:
        discussion_id = discussion.get("id")
        for note in discussion.get("notes", []):
            body = note.get("body", "")
            # Zpětná kompatibilita - hledáme staré i nové markery
            if "**RejPAL**" not in body and "**AI Review**" not in body:
                continue
            note_id = note.get("id")
            position = note.get("position")
            file_path = None
            line = None
            if position:
                file_path = position.get("new_path")
                line = position.get("new_line")
            existing.append({
                "note_id": note_id,
                "discussion_id": discussion_id,
                "file_path": file_path,
                "line": line,
            })
    return existing


def main():
    init_config()
    
    # Validace
    missing = []
    if not PROJECT_ID:
        missing.append("CI_PROJECT_ID")
    if not MR_IID:
        missing.append("CI_MERGE_REQUEST_IID")
    if not GITLAB_TOKEN:
        missing.append("GITLAB_TOKEN")
    if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
        missing.append("OPENAI_API_KEY nebo ANTHROPIC_API_KEY")
    
    if missing:
        print(f"❌ Chybí proměnné prostředí: {', '.join(missing)}")
        sys.exit(1)
    
    print(f"🔍 RejPAL pro MR !{MR_IID}")
    
    gitlab = GitLabClient(GITLAB_URL, GITLAB_TOKEN, PROJECT_ID)
    ai_client = AIClient(provider=AI_PROVIDER)
    
    mr_info = gitlab.get_mr_info(MR_IID)
    mr_changes = gitlab.get_mr_changes(MR_IID)
    
    source_branch = mr_info["source_branch"]
    diff_refs = mr_changes.get("diff_refs", {})
    base_sha = diff_refs.get("base_sha")
    head_sha = diff_refs.get("head_sha")
    start_sha = diff_refs.get("start_sha")
    
    print(f"📁 Branch: {source_branch}")
    print(f"📝 Změněných souborů: {len(mr_changes.get('changes', []))}")
    
    rules = load_review_rules()

    # Smazat existující AI komentáře (cleanup před novým review)
    discussions = gitlab.get_mr_discussions(MR_IID)
    existing_ai_comments = get_existing_ai_comments(discussions)
    deleted_count = 0
    if existing_ai_comments:
        print(f"🗑️  Mažu {len(existing_ai_comments)} starých AI komentářů...")
        for comment in existing_ai_comments:
            gitlab.delete_mr_note(MR_IID, comment["note_id"])
            deleted_count += 1
        print(f"✅ Smazáno {deleted_count} starých komentářů")

    # Najít nebo vytvořit sumář (bude první komentář = nahoře)
    notes = gitlab.get_mr_notes(MR_IID)
    summary_note_id = find_existing_summary_note(notes)
    if not summary_note_id:
        placeholder = "## RejPAL\n\n⏳ Probíhá analýza..."
        result = gitlab.create_mr_note(MR_IID, placeholder)
        summary_note_id = result.get("id")
        print("📝 Sumář vytvořen (placeholder)")
    else:
        print("📝 Existující sumář nalezen")

    total_comments = 0
    reviewed_files = 0

    for change in mr_changes.get("changes", []):
        file_path = change.get("new_path")
        diff = change.get("diff", "")

        if not should_review_file(file_path):
            print(f"⏭️  Přeskakuji: {file_path}")
            continue

        if change.get("deleted_file"):
            continue

        print(f"🔎 Analyzuji: {file_path}")
        reviewed_files += 1

        changed_lines = parse_diff_for_new_lines(diff)
        if not changed_lines:
            continue

        file_content = gitlab.get_file_content(file_path, source_branch)
        if not file_content:
            print(f"   ⚠️  Nelze načíst obsah")
            continue

        comments = analyze_with_ai(
            ai_client, file_path, file_content, diff, changed_lines, rules,
        )

        print(f"   💬 Komentářů: {len(comments)}")

        for comment in comments:
            line = comment.get("line")
            body = format_comment(comment)
            gitlab.create_mr_discussion(
                MR_IID, body, file_path, line, base_sha, head_sha, start_sha,
            )
            total_comments += 1

    print(f"\n✅ Hotovo! Souborů: {reviewed_files}, Komentářů: {total_comments}, Smazáno starých: {deleted_count}")

    # Aktualizovat sumář s finálními statistikami
    summary = f"""## RejPAL

| Metrika | Hodnota |
|---------|---------|
| Zkontrolováno souborů | {reviewed_files} |
| Připomínek | {total_comments} |
| Smazáno starých | {deleted_count} |

{"✨ Žádné významné problémy." if total_comments == 0 else "👆 Viz inline komentáře."}

<sub>Generováno automaticky</sub>
"""
    gitlab.update_mr_note(MR_IID, summary_note_id, summary)
    print("📝 Sumář aktualizován")


if __name__ == "__main__":
    main()
