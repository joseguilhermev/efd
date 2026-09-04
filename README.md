# Consolidação EFD Contribuições e validação EFD ICMS/IPI

Projeto Python gerenciado com `uv` que lê o TXT da EFD Contribuições e gera um
CSV em que os campos do documento são repetidos em cada item. A saída usa as
colunas da imagem fornecida, separador `;` e codificação UTF-8 com BOM, adequada
para abertura no Excel.

O fluxo integrado recebe também a EFD ICMS/IPI, controla o período de escopo e
destaca as notas que não foram lançadas na EFD Contribuições. O preenchimento de
um WP em Excel não faz parte desta etapa.

O conversor suporta:

- `A100/A170` — notas fiscais de serviço e seus itens;
- `C100/C170` e `C100/C175` — documentos fiscais e seus itens ou resumo
  analítico de NFC-e;
- `C180/C181/C185`, `C190/C191/C195`, `C380/C381/C385`,
  `C400/C405/C481/C485`, `C490/C491/C495`, `C500/C501/C505` e
  `C600/C601/C605` — documentos consolidados com detalhamentos de PIS e
  Cofins;
- `C395/C396`, `C800/C810`, `C800/C820`, `C860/C870` e `C860/C880` —
  documentos e detalhamentos que já trazem PIS e Cofins no mesmo registro;
- `D100/D101/D105`, `D200/D201/D205`, `D500/D501/D505` e
  `D600/D601/D605` — transportes e comunicações com detalhamentos de PIS e
  Cofins;
- `F100` — somente outras receitas (`IND_OPER` 1 ou 2);
- `F550` — consolidação das operações.

Nos grupos em que PIS e Cofins são registros irmãos, os detalhes são unidos
pelos campos comuns do leiaute (como item, CFOP, valor e natureza). Se existir
detalhamento de apenas uma contribuição, ele é preservado em uma linha parcial.
Registros cadastrais, processos referenciados, custos auxiliares e apuração dos
blocos M, P e 1 não são pares de operações analíticas e continuam fora do CSV.

O TXT sintético que acompanha o projeto não usa integralmente as posições do
leiaute oficial. Por isso, A100/A170, C100/C170 e F100 possuem dois esquemas
aceitos: o oficial e o compacto da amostra. A quantidade de campos é validada;
um terceiro formato desconhecido interrompe a conversão com o número da linha,
em vez de deslocar colunas silenciosamente.

## Uso

Separe os arquivos mensais em duas subpastas com estes nomes:

```text
entrada/
├── efd_contribuicoes/
│   ├── efd_01_2026.txt
│   ├── efd_02_2026.txt
│   └── ...
└── efd_icms/
    ├── efd_01_2026.txt
    ├── efd_02_2026.txt
    └── ...
```

Os nomes dos arquivos são livres. O período, o tipo da EFD e o CNPJ são lidos
do conteúdo. Todos os arquivos devem pertencer ao mesmo CNPJ e ao mesmo ano, e
só pode existir um arquivo de cada EFD por mês.

Na pasta do projeto, execute todo o fluxo por uma única entrada:

```bash
uv sync
uv run efd-processar entrada --diretorio-saida resultado
```

O mesmo fluxo pode ser chamado como módulo:

```bash
uv run python -m efd_contribuicoes_csv entrada --diretorio-saida resultado
```

Antes de gerar qualquer CSV, o programa valida todos os arquivos e considera os
12 meses do ano identificado. Se faltar algum período, informa separadamente os
meses ausentes na EFD Contribuições e na EFD ICMS/IPI e pergunta:

```text
Continuar mesmo assim? [s/N]
```

Uma resposta diferente de `s` ou `sim` cancela o processamento sem criar os
CSVs. Em execução automatizada, a confirmação pode ser dispensada:

```bash
uv run efd-processar entrada --continuar-com-ausentes
```

Ano divergente, CNPJ divergente, período duplicado, pasta ausente, tipo de EFD
incorreto ou arquivo inválido impedem o processamento e são apresentados antes
da geração das saídas. Quando a continuação com meses ausentes é autorizada,
somente os períodos disponíveis são consolidados e somente os meses que possuem
as duas EFDs são comparados.

O fluxo cria:

- `efd_contribuicoes_analitico.csv`;
- `efd_contribuicoes_indicadores.csv`;
- `efd_comparacao_notas.csv`;
- `efd_icms_nao_lancadas_contribuicoes.csv`;
- `efd_periodos_escopo.csv`.

O controle de escopo sempre possui janeiro a dezembro. Meses sem EFD
Contribuições aparecem como `AUSENTE` e recebem uma linha zerada para cada
indicador.

Os filtros de CFOP também estão disponíveis no fluxo integrado:

```bash
uv run efd-processar entrada \
  --cfop-incluir 5101,5102,6101,6102 \
  --cfop-excluir 5102
```

Sem filtro, são aceitos os CFOPs cuja classificação oficial representa venda de
produto, energia, combustível ou exportação. Transferências, remessas,
devoluções, vendas de ativo imobilizado e simples faturamento não são tratados
como receita de venda para produto. A exclusão prevalece sobre a inclusão, mas
um filtro de inclusão não transforma uma operação que não seja venda em venda.

Para rodar os testes:

```bash
uv run pytest
```

A fixture `tests/fixtures/efd_contribuicoes_outros_pares.txt` contém uma
operação mínima de cada agrupamento pai/filho adicional, com dados inteiramente
fictícios.

## Comparação de notas com a EFD ICMS/IPI

O fluxo compara uma nota por registro `C100`, sem repetir os itens `C170`:

Para NF-e e NFC-e, a identificação usa `CNPJ do estabelecimento + CHV_NFE`.
Nos modelos sem chave eletrônica, usa `CNPJ do estabelecimento + documento do
participante + modelo + série + número`. Quando a EFD Contribuições contém
vários estabelecimentos, são comparadas somente as notas do CNPJ informado no
registro `0000` da EFD ICMS/IPI.

O CSV informa os valores das duas escriturações lado a lado e atribui um dos
seguintes status:

- `CONFERENTE`: os campos comparados são iguais;
- `DIVERGENTE`: operação, emitente, modelo, situação, série, número, datas ou
  valor do documento são diferentes;
- `SOMENTE_EFD_CONTRIBUICOES` ou `SOMENTE_EFD_ICMS`: a nota existe em apenas um
  arquivo;
- `DUPLICADA_EFD_CONTRIBUICOES`, `DUPLICADA_EFD_ICMS` ou `DUPLICADA_AMBAS`: a
  chave documental aparece mais de uma vez no mesmo arquivo.

O comparador aceita o `C100` oficial de 29 campos e a variante compacta de 28
campos apenas na EFD Contribuições sintética fornecida. Na EFD ICMS/IPI são
exigidos os 29 campos oficiais e chaves eletrônicas com 44 dígitos. Arquivos de
períodos diferentes são rejeitados para evitar uma comparação enganosa.

O arquivo `efd_icms_sintetico_estrutura_real.txt` é uma massa de teste focada
nos registros `0000`, `0150`, `C100`, `C190` e nos encerramentos dos blocos. Ele
usa a estrutura de campos vigente, mas contém inscrições e valores fictícios e
não deve ser transmitido nem tratado como arquivo homologado pelo PVA.

## Regras relevantes

- O programa não converte códigos, documentos, CNPJ/CPF ou chaves em números,
  preservando todos os caracteres existentes no TXT (inclusive CNPJ
  alfanumérico).
- Datas `DDMMAAAA` são apresentadas como `DD/MM/AAAA`; valores decimais mantêm a
  vírgula original da EFD.
- `UF Origem/Destino` é obtida do código IBGE do município no registro `0150`.
  Na amostra compacta, que não traz esse código, é lida do prefixo do campo
  sintético como `RJ MUNICIPIO TESTE`.
- `Débito/Crédito` é derivado de `IND_OPER`: `0` gera crédito, `1` gera débito e
  `2` (receita sem contribuição) fica vazio. No F550, só há débito para CST de
  receita tributada (`01`, `02`, `03` ou `05`).
- `CFOP Faturamento` não existe no leiaute oficial; ele só é preenchido quando a
  variante compacta fornecida contém esse campo de negócio.
- O resumo exibido ao final sempre informa todos os grupos suportados, com
  contagem zero para os que não estiverem preenchidos. O CSV analítico não recebe linhas
  fiscais fictícias; somente o CSV de indicadores recebe linhas zeradas para
  manter todos os indicadores e períodos do escopo visíveis.
- `A100` ou `C100` sem o respectivo item `A170` ou `C170` não gera linha no CSV;
  isso evita misturar documentos cancelados ou detalhados por registros fora do
  escopo com a tabela analítica por item.
- Registros diferentes dos grupos operacionais definidos no escopo são ignorados.
- No F550, `VL_REC_COMP` alimenta apenas `Vlr Mercadoria/Operação`; os descontos
  específicos de PIS e Cofins não são tratados como desconto de item.

## Indicadores

O segundo CSV classifica e agrupa somente operações de saída (`Tipo Operação =
1`) pelas seguintes regras:

- `A100/A170`: receita de venda para serviço;
- `C100/C170`: receita de venda para produto quando a natureza oficial do CFOP
  representar venda, respeitando também os filtros de inclusão e exclusão;
- `F100` com `CST PIS = 02` e `Alíquota Cofins = 4`:
  receitas financeiras;
- `F100` com `CST PIS` diferente de `02`: outras receitas, agrupadas por CST.

Um `F100` com `CST PIS = 02` e `Alíquota Cofins` diferente de `4` não pertence a
nenhum dos dois últimos indicadores. O `F550` continua
no CSV analítico, mas não participa desses indicadores.

As vendas são agrupadas por estabelecimento, período, CST PIS, CFOP e item. No
caso do `A100/A170`, o `CFOP Faturamento` é usado quando o CFOP estiver vazio.
Cada linha de venda apresenta `Descrição CFOP`, `Âmbito CFOP` e `Classificação
CFOP`. O âmbito distingue entradas e saídas internas, interestaduais e com o
exterior; a classificação corresponde ao grupo oficial da natureza fiscal. As
outras receitas são agrupadas por CST PIS. `Quantidade Registros` informa
quantas linhas analíticas compõem cada grupo.

Quando um tipo de registro não estiver preenchido em um mês, seu indicador é
gravado com quantidade e valores iguais a zero. Isso também ocorre para todos
os indicadores dos meses sem processamento dentro do período de escopo.

Para evitar duplicar documentos com vários itens, `Valor Operação` usa `Vlr
Item` nos pares A/C e `Vlr Mercadoria/Operação` no F100. Os valores são somados
com precisão decimal.

O mapeamento oficial foi baseado no [Guia Prático da EFD-Contribuições v1.35 da
Receita Federal](https://www.gov.br/sped/pt-br/assuntos/escrituracoes-digitais/efd-contribuicoes/manuais/guia_pratico_efd_contribuicoes_versao_1_35-18_06_2021.pdf).
O catálogo de 619 CFOPs, suas descrições e classificações segue o [Anexo II do
Convênio s/nº de 1970, na redação do Ajuste SINIEF 03/24, versão 2.0 da
SEF/SC](https://www.sef.sc.gov.br/orientacoes/codigos-fiscais-de-operacoes-e-prestacoes-cfop).
A estrutura da massa ICMS e as regras do `C100` foram baseadas no [Guia Prático
da EFD ICMS/IPI v3.2.2](https://www.gov.br/sped/pt-br/assuntos/escrituracoes-digitais/efd-icms-ipi/manuais-e-documentos-tecnicos/guia-pratico-da-efd-icms-ipi-3-2.2),
vigente a partir de 2026.
