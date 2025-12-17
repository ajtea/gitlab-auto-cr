FROM python:3.11-slim

LABEL maintainer="thecnology"
LABEL description="AI Code Review for GitLab MR"

# Nastavení pracovního adresáře
WORKDIR /app

# Kopírování requirements a instalace závislostí
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopírování aplikace
COPY code_review.py .
COPY review_rules.md /app/default_rules.md

# Výchozí pravidla - lze přepsat pomocí REVIEW_RULES_FILE nebo mountem
ENV REVIEW_RULES_FILE=/app/default_rules.md

# Entrypoint
ENTRYPOINT ["python", "/app/code_review.py"]
