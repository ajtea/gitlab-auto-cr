# AI Code Review - Docker Image

Docker image pro automatický AI code review v GitLab CI/CD.

**Výhoda:** Žádný kód v projektech - jen pár řádků v `.gitlab-ci.yml`.

## Quick Start

### 1. Build a push image do GitLab Registry

# Aktualně nalezneš multiarch verzi na dockerhubu:  djvitto/claude-gitlab-auto-cr
```bash
# Klonuj/stáhni tento adresář
cd gitlab-auto-cr

# Login do GitLab Container Registry
docker login registry.gitlab.com

# Build image
docker build -t u-name-it/ai-code-review:latest .

# Push
docker push u-name-it/ai-code-review:latest
```

### 2. Nastav CI/CD Variables (na úrovni skupiny)

V GitLabu: **Group → Settings → CI/CD → Variables**

| Variable | Hodnota | Flags |
|----------|---------|-------|
| `GITLAB_TOKEN` | Personal/Group Access Token | Masked |
| `OPENAI_API_KEY` | API klíč z OpenAI | Masked |

> 💡 Nastavením na úrovni **skupiny** budou variables dostupné ve všech projektech.

### 3. Přidej do `.gitlab-ci.yml` v projektu

```yaml
ai-code-review:
  stage: review
  image: djvitto/claude-gitlab-auto-cr:latest
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: true
```

**To je vše!** 🎉

---

## Konfigurace

### Volitelné ENV proměnné

| Variable | Default | Popis |
|----------|---------|-------|
| `AI_PROVIDER` | `auto` | `openai` / `anthropic` / `auto` |
| `OPENAI_MODEL` | `gpt-4o` | Model pro OpenAI |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model pro Anthropic |
| `REVIEW_LANGUAGE` | `cs` | Jazyk komentářů: `cs` / `en` |
| `IGNORE_PATTERNS` | - | Extra patterns k ignorování (čárkami) |
| `REVIEW_EXTENSIONS` | - | Extra přípony k review (čárkami) |
| `MAX_FILE_SIZE` | `50000` | Max velikost souboru (chars) |

### Příklad s konfigurací

```yaml
ai-code-review:
  stage: review
  image: djvitto/claude-gitlab-auto-cr:latest
  variables:
    OPENAI_MODEL: "gpt-4o-mini"  # levnější model
    REVIEW_LANGUAGE: "en"         # anglické komentáře
    IGNORE_PATTERNS: "tests/,*.spec.ts"  # ignorovat testy
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: true
```

---

## Vlastní pravidla

### Možnost 1: Soubor v projektu

Přidej `review_rules.md` do kořene projektu - automaticky se použije místo defaultních pravidel.

```
my-project/
├── review_rules.md   ← vlastní pravidla
├── src/
└── .gitlab-ci.yml
```

### Možnost 2: ENV proměnná

```yaml
ai-code-review:
  variables:
    REVIEW_RULES_CONTENT: |
      ## Naše pravidla
      - Vždy používej TypeScript
      - Komponenty max 100 řádků
      - Žádné any typy
```

### Možnost 3: Vlastní image

Fork této image a uprav `review_rules.md` přímo v ní.

---

## Pokročilé použití

### Různé pravidla pro různé projekty

```yaml
# Pro backend projekty
ai-code-review:
  extends: .ai-review-base
  variables:
    REVIEW_RULES_FILE: /app/rules/backend.md

# Pro frontend projekty  
ai-code-review:
  extends: .ai-review-base
  variables:
    REVIEW_RULES_FILE: /app/rules/frontend.md
```

### Spuštění pouze pro určité větve

```yaml
ai-code-review:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      when: always
    - if: $CI_COMMIT_BRANCH == "develop"
      when: manual
```

### Blokující review (ne doporučeno pro začátek)

```yaml
ai-code-review:
  allow_failure: false  # MR nelze mergovat při chybě
```

---

## Struktura image

```
/app/
├── code_review.py      # hlavní skript
├── default_rules.md    # výchozí pravidla
└── requirements.txt
```

---

## Troubleshooting

### "Permission denied" při push do registry
```bash
docker login registry.gitlab.com -u YOUR_USERNAME -p YOUR_ACCESS_TOKEN
```

### Komentáře se nezobrazují
- Zkontroluj `GITLAB_TOKEN` - potřebuje `api` scope
- Podívej se do pipeline logu

### Rate limiting od OpenAI
- Použij levnější model: `OPENAI_MODEL: "gpt-4o-mini"`
- Přidej více ignorovaných souborů

### Review trvá příliš dlouho
- Přidej `IGNORE_PATTERNS: "tests/,*.test.ts,*.spec.ts"`
- Sniž `MAX_FILE_SIZE`

---

## Náklady

Přibližné náklady za review jednoho MR (~10 souborů):

| Model | Cena |
|-------|------|
| gpt-4o | ~$0.05 |
| gpt-4o-mini | ~$0.005 |
| claude-sonnet | ~$0.04 |

---

## CI/CD Template (bonus)

Vytvoř v repozitáři s image soubor `gitlab-ci-template.yml`:

```yaml
# Include v projektech: include: 'https://gitlab.com/SKUPINA/ai-code-review/-/raw/main/gitlab-ci-template.yml'

.ai-code-review:
  stage: review
  image: djvitto/claude-gitlab-auto-cr:latest
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: true
```

Pak v projektech stačí:

```yaml
include:
  - project: 'tvoje-skupina/ai-code-review'
    file: 'gitlab-ci-template.yml'

ai-code-review:
  extends: .ai-code-review
```
