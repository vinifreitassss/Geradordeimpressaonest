# Gerador de Impressão Nest

Aplicação local em Python para montar pedidos de impressão/corte em blocos identificados e fazer o nest desses blocos em folhas de **450 mm de largura** e **altura variável de até 600 mm**.

## Regras atuais

- Cada produto possui nome e PDF base do corte.
- O tamanho físico usado pelo nest é lido automaticamente da página do PDF de corte; o app não deve redimensionar o template pelo nome comercial do produto.
- O PDF de corte precisa conter a spot color **CutContour** como `/Separation`.
- Espaçamento fixo entre peças: **2 mm**.
- Todos os blocos podem ser rotacionados pelo nest.
- A arte ocupa a caixa inteira da peça e o operador pode ajustar escala e deslocamento.
- Cada pedido permanece agrupado em um único bloco retangular.
- Cada bloco recebe uma linha fina externa e uma tarja compacta com pedido, produto, quantidade, detalhes e Code128.
- O nest externo considera apenas aproveitamento geométrico/área.
- Pedidos ficam em uma fila local até o operador clicar em **Gerar nest**.
- O resultado final é PDF.

## Validação com os templates reais da Roland

Foram inspecionados os templates enviados da produção:

- `linhacorte-med5cm.pdf` — página ~46 × 46 mm; contorno efetivo ~45 mm.
- `linhacorte-med6cm.pdf` — página ~56 × 56 mm; contorno efetivo ~55 mm.
- `linhacorte-med7cm.pdf` — página ~66 × 66 mm; contorno efetivo ~65 mm.
- `linhacorte-med8cm.pdf` — página ~76 × 76 mm; contorno efetivo ~75 mm.
- `linhacorte-TRF210-45cm.pdf` — página ~185 × 185 mm.

Todos usam a separação especial `/CutContour`. Um teste de composição com `PyMuPDF.Page.show_pdf_page()` confirmou que a saída continua contendo `/Separation /CutContour`, ou seja, o template não é rasterizado na composição.

Isso ainda deve ser validado em uma impressão/corte real antes de liberar o sistema em produção.

## Como instalar no PC servidor

Requer Python 3.11 ou mais recente.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

No próprio PC, abra:

```text
http://127.0.0.1:8000
```

Nos outros computadores da mesma rede, abra o IP do PC servidor, por exemplo:

```text
http://192.168.0.50:8000
```

Para descobrir o IP no Windows:

```bat
ipconfig
```

Procure o endereço IPv4 da placa de rede em uso. Se o Windows Firewall perguntar, permita o Python/Uvicorn em redes privadas.

## Fluxo

1. Cadastre um modelo informando o nome e o PDF de corte.
2. O app valida a existência de `CutContour` e lê as dimensões físicas do próprio PDF.
3. Crie um pedido, selecione o modelo, quantidade e envie a arte.
4. Ajuste escala e posição da arte no preview.
5. Adicione o pedido à fila.
6. Repita para quantos pedidos quiser.
7. Clique em **Gerar nest**.
8. O sistema cria uma ou mais folhas PDF de 450 mm × altura necessária, limitada a 600 mm.

## Armazenamento

Não há banco SQL nesta versão. Tudo é salvo localmente em `data/`:

```text
data/
  models.json       cadastro dos produtos
  models/           PDFs de corte
  uploads/          artes enviadas
  orders/           um JSON por pedido
  output/           PDFs gerados
```

Isso deixa a instalação simples e facilita backup: basta copiar a pasta `data`.

## Arquitetura

- `app.py` — servidor FastAPI + interface web.
- `storage.py` — persistência simples em JSON/arquivos e validação dos templates de corte.
- `nest.py` — criação do bloco do pedido e MaxRects para encaixe das ordens nas folhas.
- `pdf_engine.py` — composição da arte, sobreposição do PDF de corte, identificação, código de barras e PDF final.

## Observação importante sobre a Roland

O sistema preserva o PDF de corte cadastrado e o sobrepõe à arte mantendo a separação especial `CutContour` nos testes estruturais. Antes do uso em produção, faça um teste físico na Roland com uma folha simples para confirmar que o VersaWorks/fluxo atual reconhece corretamente o contorno no PDF final gerado pelo app.
