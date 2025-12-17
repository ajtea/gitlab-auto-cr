# Pravidla pro AI Code Review

## Obecné principy

### SOLID
- Single Responsibility - třída/funkce má jednu odpovědnost
- Open/Closed - otevřené pro rozšíření, uzavřené pro modifikaci  
- Liskov Substitution - podtřídy musí být zaměnitelné
- Interface Segregation - více specifických rozhraní
- Dependency Inversion - závisej na abstrakcích

### DRY & KISS
- Neopakuj se - duplicitní kód extrahuj
- Udržuj věci jednoduché

---

## PHP / Laravel

### Architektura
- Controllers - tenké, max 10-15 řádků na metodu
- Form Requests - veškerá validace patří sem
- Services - business logika zde, ne v controllerech
- Models - pouze vztahy, accessory, scopes. Žádná business logika!

### Best Practices
- Route Model Binding místo ručního hledání
- Eloquent relationships místo raw joinů
- Policies pro autorizaci
- Events & Listeners pro side effects
- Jobs pro dlouhotrvající operace
- Resources pro API responses

### Eloquent
- N+1 problém - vždy eager loading (with())
- Mass assignment - definuj $fillable nebo $guarded

### Čeho si všímat
- God classes - příliš velké controllery/modely
- Business logika v modelech
- Přímé DB dotazy v controlleru
- Chybějící type hints (PHP 8+)
- Zbytečné proměnné před return (např. `$data = ...; return $data;` → `return ...;`)
- Redundantní kód který lze zjednodušit

---

## Vue.js / Inertia.js

### Komponenty
- Composables pro reusable logiku (use*)
- Max 200-300 řádků na komponentu
- Props down, events up

### Composition API
- Preferuj <script setup>
- Logicky seskupuj related kód

### Inertia specifika
- useForm() pro formuláře
- Partial reloads kde to dává smysl

### Čeho si všímat
- Příliš velké komponenty
- Business logika v template
- Chybějící loading/error states
- Správné použití ref() vs reactive()

---

## Bezpečnost
- Žádné hardcoded credentials
- Validace vstupů
- Autorizace na každém endpointu

## Co NEKOMENTOVAT
- Formátování (řeší linter)
- Import ordering
- Trailing whitespace
