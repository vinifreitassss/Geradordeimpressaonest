# Gerador de Impressão Nest

Ferramenta web para montar pedidos de impressão/corte em blocos identificados e fazer o nest desses blocos em folhas de **450 mm de largura** e **altura variável de até 600 mm**.

## Objetivo da aplicação

O Gerador é uma ferramenta de processamento, não um sistema de armazenamento.

- O usuário abre a ferramenta pela web.
- Os PDFs de corte, artes e dados dos pedidos são enviados somente para a execução atual.
- O processamento acontece em uma função Python/FastAPI na Vercel.
- O PDF final é devolvido ao navegador para download.
- O usuário salva a folha de impressão no próprio computador.
- Não existe banco de dados, login, histórico ou armazenamento permanente de pedidos, artes ou PDFs gerados.
- Atualizar/fechar a página encerra a sessão do navegador e a fila desaparece.

A execução usa diretórios temporários por requisição. Ao terminar o processamento, esses arquivos deixam de fazer parte da aplicação.

## Regras atuais

- Cada produto possui nome e PDF base do corte.
- O tamanho físico usado pelo nest é lido automaticamente da página do PDF de corte; o app não redimensiona o template pelo nome comercial do produto.
- O PDF de corte precisa conter a spot color **CutContour** como `/Separation`.
- Espaçamento fixo entre peças: **2 mm**.
- O nest cria blocos horizontais e pode dividir pedidos grandes em partes quando necessário.
- A arte ocupa a caixa da peça e o operador pode ajustar escala, deslocamento e rotação.
- Cada pedido permanece agrupado em um único bloco retangular.
- Cada bloco recebe uma linha fina externa e uma tarja compacta com pedido, produto, quantidade, detalhes e Code128.
- O nest externo considera aproveitamento geométrico/área.
- O resultado final é um único PDF multipágina para a sessão.

## Arquitetura online

```text
Navegador
   |
   | PDF de corte + artes + pedidos
   v
Vercel / FastAPI
   |
   +-- PyMuPDF
   +-- Pillow
   +-- rectpack
   +-- python-barcode
   |
   v
PDF final
   |
   v
Download no navegador
```

Arquivos importantes:

- `index.html` — interface web, mantendo a fila somente na memória do navegador.
- `api/index.py` — função FastAPI executada pela Vercel.
- `nest.py` — criação dos blocos e encaixe MaxRects.
- `pdf_engine.py` — composição da arte, preservação do PDF de corte, identificação, código de barras e PDF final.
- `storage.py` — somente validação dos PDFs e definição dos presets; não existe mais persistência de pedidos/modelos.
- `presets/` — templates de corte que fazem parte da própria ferramenta.

## Presets incluídos

- `linhacorte-med5cm.pdf` — página ~46 × 46 mm; contorno efetivo ~45 mm.
- `linhacorte-med6cm.pdf` — página ~56 × 56 mm; contorno efetivo ~55 mm.
- `linhacorte-med7cm.pdf` — página ~66 × 66 mm; contorno efetivo ~65 mm.
- `linhacorte-med8cm.pdf` — página ~76 × 76 mm; contorno efetivo ~75 mm.
- `linhacorte-TRF210-45cm.pdf` — página ~185 × 185 mm.

Todos usam a separação especial `/CutContour`.

## Desenvolvimento local

Requer Python 3.11 ou mais recente.

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

O servidor local expõe a API em `http://127.0.0.1:8000`. A interface web pode ser aberta diretamente pelo `index.html` durante o desenvolvimento ou por uma implantação Vercel.

## Deploy na Vercel

A Vercel reconhece funções Python no diretório `api/`. O arquivo `api/index.py` contém uma variável ASGI chamada `app`, que é o padrão esperado pelo runtime Python da Vercel.

A interface fica na raiz como `index.html` e chama os endpoints no mesmo domínio:

- `/api` — saúde/configuração básica.
- `/api/presets` — lista os presets que fazem parte do projeto.
- `/api/inspect-model` — valida temporariamente um PDF de corte enviado pelo usuário.
- `/api/generate` — recebe a sessão atual, executa o nest e devolve o PDF.

Não são necessárias variáveis de ambiente, banco de dados ou storage externo para o funcionamento básico.

## Validação da Roland

O sistema preserva o PDF de corte cadastrado e o sobrepõe à arte mantendo a separação especial `CutContour`. O comportamento estrutural já havia sido validado com `PyMuPDF.Page.show_pdf_page()`.

Antes do uso em produção, faça um teste físico na Roland com uma folha simples para confirmar que o VersaWorks/fluxo atual reconhece corretamente o contorno no PDF final gerado pelo app.
