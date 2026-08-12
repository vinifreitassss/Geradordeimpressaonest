# Gerador de Impressão Nest

Aplicação local em Python para montar pedidos de impressão/corte em blocos identificados e fazer o nest desses blocos em folhas de **450 mm de largura** e **altura variável de até 600 mm**.

## Regras atuais

- Cada produto possui somente: nome, largura, altura e PDF base do corte.
- Espaçamento fixo entre peças: **2 mm**.
- Todos os blocos podem ser rotacionados pelo nest.
- A arte ocupa a caixa inteira da peça e o operador pode ajustar escala e deslocamento.
- Cada pedido permanece agrupado em um único bloco retangular.
- Cada bloco recebe uma linha fina externa e uma tarja compacta com pedido, produto, quantidade, detalhes e Code128.
- O nest externo considera apenas aproveitamento geométrico/área.
- Pedidos ficam em uma fila local até o operador clicar em **Gerar nest**.
- O resultado final é PDF.

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

1. Cadastre um modelo informando nome, largura, altura e o PDF de corte.
2. Crie um pedido, selecione o modelo, quantidade e envie a arte.
3. Ajuste escala e posição da arte no preview.
4. Adicione o pedido à fila.
5. Repita para quantos pedidos quiser.
6. Clique em **Gerar nest**.
7. O sistema cria uma ou mais folhas PDF de 450 mm × altura necessária, limitada a 600 mm.

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
- `storage.py` — persistência simples em JSON/arquivos.
- `nest.py` — criação do bloco do pedido e MaxRects para encaixe das ordens nas folhas.
- `pdf_engine.py` — composição da arte, sobreposição do PDF de corte, identificação, código de barras e PDF final.

## Observação importante sobre a Roland

O sistema preserva o PDF de corte cadastrado e o sobrepõe à arte. Antes de usar em produção, faça um teste com um PDF de corte real da Roland para confirmar que a convenção usada pela máquina (cor spot/nome da linha/camada, conforme seu fluxo atual) continua preservada após a composição pelo PyMuPDF.
