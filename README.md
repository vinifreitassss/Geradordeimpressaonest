# Gerador de Impressão Nest

Ferramenta web para montar pedidos de impressão/corte e fazer o nest em folhas de **450 mm de largura** e **altura variável de até 600 mm**.

## Diretriz principal

O processamento de produção acontece **no navegador do usuário**.

- Vercel fornece a interface, os presets e apenas metadados.
- Artes, PDFs de corte, pedidos e a fila ficam na sessão do navegador.
- O PDF final é criado no navegador e baixado diretamente no computador do usuário.
- A aplicação não envia a arte do usuário para `/api/generate` e não mantém banco, histórico ou storage de produção.

## Fluxo

1. O usuário escolhe **Usar modelo de corte** ou **Já está com linha de corte**.
2. No primeiro modo, seleciona um preset e anexa a arte; a arte é ajustada/máscarada pelo contorno e o `CutContour` original é sobreposto.
3. No segundo modo, o PDF enviado já é considerado uma peça pronta; o app apenas multiplica, identifica e faz o nest.
4. Pedidos entram em uma fila local da página.
5. O nest procura o maior aproveitamento possível de cada folha de 450 × 600 mm.
6. Um pedido pode ser dividido em quantos grupos forem necessários. Cada grupo recebe `PARTE X/Y` e continua visualmente fechado por um retângulo de identificação.
7. O resultado é um único PDF multipágina.

## Regras de produção

- Largura da folha: **450 mm fixa**.
- Altura máxima: **600 mm**.
- Espaçamento entre peças: **2 mm**.
- Todos os modelos podem ser orientados nas duas direções quando isso melhora o encaixe; a folha continua horizontal, com 450 mm de largura.
- O tamanho físico do preset é lido do próprio PDF; o app não redimensiona o corte pelo nome comercial.
- Os presets da Roland usam a spot color **CutContour** como `/Separation`.
- A linha externa de cada grupo é fina e serve para identificação/organização do pedido, não como linha de corte da Roland.
- A tarja contém pedido, produto, quantidade do grupo, parte e detalhes; o código do pedido também recebe Code128.
- O objetivo do nest é geométrico: reduzir folhas e maximizar ocupação, sem filtros de material/prioridade.

## Nest por grupos

O pedido não é tratado como bloco indivisível.

```text
PEDIDO 775637 — 100 peças
        |
        +-- grupo 1: 42 peças
        +-- grupo 2: 48 peças
        +-- grupo 3: 10 peças
                |
                v
        NEST DAS FOLHAS
```

Os tamanhos dos grupos são escolhidos para permitir que pedidos diferentes ocupem a mesma folha quando houver espaço. Portanto um pedido pequeno pode ser encaixado junto de uma parte de um pedido grande, enquanto o restante continua na folha seguinte.

## Arquitetura Vercel

```text
                 VERCEL
       ┌──────────────────────┐
       │ index.html           │
       │ presets/             │
       │ /api/presets         │
       └──────────┬───────────┘
                  │ metadados/templates
                  v
             NAVEGADOR
       ┌──────────────────────┐
       │ fila de pedidos      │
       │ ajuste da arte       │
       │ nest                  │
       │ PDF-LIB               │
       │ PDF.js                │
       │ máscara               │
       │ PDF final             │
       └──────────┬───────────┘
                  │
                  v
          download local
```

O `api/index.py` é **metadata-only**: ele lista os presets e suas dimensões. Não existe endpoint de geração de PDF de produção.

## Arquivos importantes

- `index.html` — interface e processamento de produção no navegador.
- `packer.js` — motor MaxRects leve, servido pela própria aplicação.
- `api/index.py` — API mínima para presets.
- `storage.py` — validação e definição dos presets.
- `presets/` — PDFs de corte da Roland.
- `nest.py` e `pdf_engine.py` — implementação Python anterior, mantida como referência técnica; o fluxo web atual não os utiliza para gerar a produção.

## Presets incluídos

- `linhacorte-med5cm.pdf` — página ~46 × 46 mm; contorno efetivo ~45 mm.
- `linhacorte-med6cm.pdf` — página ~56 × 56 mm; contorno efetivo ~55 mm.
- `linhacorte-med7cm.pdf` — página ~66 × 66 mm; contorno efetivo ~65 mm.
- `linhacorte-med8cm.pdf` — página ~76 × 76 mm; contorno efetivo ~75 mm.
- `linhacorte-TRF210-45cm.pdf` — página ~185 × 185 mm.

## Desenvolvimento local

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Deploy

O projeto está preparado para a Vercel com `index.html` na raiz, `api/index.py` como função ASGI e `vercel.json` para o roteamento da API.

## Observação crítica sobre a Roland

O app preserva o PDF vetorial de corte e o usa como camada superior no PDF final. Como a função de geração agora roda no navegador, o primeiro teste físico na Roland deve verificar especialmente se o PDF final continua carregando a separação especial `CutContour` depois de passar pelo `pdf-lib`. Essa validação é obrigatória antes de considerar o fluxo de produção fechado.
