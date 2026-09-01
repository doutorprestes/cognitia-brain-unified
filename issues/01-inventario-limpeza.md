# Issue #1 — Inventário e Limpeza

**Labels:** `fase-1`, `inventario`, `limpeza`
**Estimate:** 2h

## Descrição

Mapear todo o código importado dos 7 projetos, identificar sobreposões, código morto e padronizar a estrutura de diretórios.

## Tarefas

- [ ] Listar todos os scrapers por projeto e fonte de dados
- [ ] Identificar sobreposições (ex: FINEP aparece em GrantWatch, IA-Brasil, inteligencia-ai)
- [ ] Mapear dependências de cada módulo
- [ ] Remover código morto e arquivos não utilizados
- [ ] Padronizar nomenclatura de diretórios e arquivos
- [ ] Criar documento de arquitetura atual (como-está)

## Critérios de Aceite

- [ ] Inventário completo de todos os scrapers e fontes
- [ ] Lista de sobreposições e duplicações identificada
- [ ] Código morto removido
- [ ] Documento de arquitetura criado em `docs/arquitetura-atual.md`

## Output Esperado

```
docs/
└── arquitetura-atual.md    # diagrama e descrição do estado atual
src/
├── scrapers/               # scrapers consolidados
├── ml/                     # classificadores
├── bot/                    # bot Telegram
├── web/                    # dashboard
└── shared/                 # código compartilhado
```
