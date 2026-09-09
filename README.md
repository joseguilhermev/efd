# Consolidação EFD Contribuições e validação EFD ICMS/IPI

Projeto Python gerenciado com `uv` que lê o TXT da EFD Contribuições e gera um
CSV em que os campos do documento são repetidos em cada item. A saída usa as
colunas da imagem fornecida, separador `;` e codificação UTF-8 com BOM, adequada
para abertura no Excel.

O fluxo integrado recebe também a EFD ICMS/IPI, controla o período de escopo e
destaca documentos não localizados na EFD Contribuições e casos que exigem revisão. O preenchimento de
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
do conteúdo. Todos os arquivos devem pertencer à mesma raiz de CNPJ (as oito
primeiras posições) e ao mesmo ano, permitindo combinar matriz e filiais. Só
pode existir um arquivo de cada EFD por mês. Uma subpasta pode estar vazia,
mas deve existir pelo menos uma EFD válida na entrada.

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

Ano divergente, raiz de CNPJ divergente, período duplicado, pasta ausente, tipo
de EFD incorreto ou arquivo inválido impedem o processamento e são apresentados
antes da geração das saídas. Quando a continuação com meses ausentes é autorizada,
todos os períodos disponíveis são processados. Meses sem uma das EFDs mantêm
os documentos disponíveis como pendências, sem concluir que as notas estão ausentes.

As datas inicial e final devem ser válidas, estar em ordem e pertencer ao mesmo
mês. Os fluxos integrado e anual geram os relatórios em uma pasta temporária;
erros durante a conversão, comparação ou criação do Excel preservam as saídas
anteriores. A substituição dos arquivos começa somente após concluir essa geração.

O fluxo cria:

- `efd_contribuicoes_analitico.csv`;
- `efd_contribuicoes_indicadores.csv`;
- `efd_comparacao_notas.csv`;
- `efd_icms_nao_lancadas_contribuicoes.csv`;
- `efd_pendencias_conferencia.csv`;
- `efd_cobertura_registros.csv`;
- `efd_periodos_escopo.csv`;
- `efd_resultado.xlsx`, com as abas `Analítico`, `Indicadores`, `Comparação`,
  `Não lançadas`, `Pendências`, `Cobertura` e `Períodos`.

A saída de notas não lançadas também inclui notas duplicadas no ICMS quando
não existe correspondência nem evidência alternativa compatível nas Contribuições,
preservando o status de duplicidade e as quantidades de cada escrituração.

Os CSVs continuam disponíveis para integrações. Para uso direto no Excel, abra
o arquivo `.xlsx`: CNPJ, CPF, chaves, números de documento e demais códigos são
gravados como texto, evitando notação científica e perda de zeros ou dígitos.
Datas e valores são gravados com tipos próprios de planilha, permitindo filtros,
ordenação e cálculos.

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

## Comparação documental com a EFD ICMS/IPI

A conferência lê os documentos diretamente dos TXT, independentemente de terem
itens no CSV analítico. Os filtros de CFOP dos indicadores não retiram documentos
da comparação. São preservadas operações de entrada e saída e a situação fiscal,
inclusive cancelamentos.

| Documentos identificados no ICMS | Registros |
| --- | --- |
| Notas de mercadorias, NF-e e NFC-e | C100 |
| Notas de serviços do bloco B | B020 |
| Notas de venda a consumidor e cupons ECF | C350, C460 e complemento de chave C465 |
| Energia, água e gás, incluindo NF3e | C500 |
| Cupons SAT | C800 |
| Documentos de transporte | D100 |
| Comunicação e telecomunicação | D500 e D700 (NFCom) |
| Números cancelados informados nos resumos | C310, C601, D301 e D411, com identificação do registro pai |

Nas Contribuições, são procurados os documentos individuais A100, C100, C395,
C500, C800, D100 e D500. A correspondência pode ocorrer entre registros diferentes:
por exemplo, uma NF-e de energia no C100 do ICMS pode estar no C500 das
Contribuições. Não se presume que todo modelo tenha um equivalente individual.

A identificação prioriza a chave eletrônica e a raiz do CNPJ. Chaves de NFS-e
são separadas das chaves de mercadorias. Na falta de chave em um dos lados, só
há associação quando a identificação documental é única: emitente, participante,
modelo/família, série, subsérie, número, ano da emissão e equipamento, quando
aplicável. Códigos locais de participantes não substituem CNPJ/CPF. Os cadastros
0150 das Contribuições respeitam o estabelecimento do 0140. Zeros à esquerda
são normalizados apenas na comparação de série e número; a saída mantém o original.

Na execução anual, uma chave eletrônica não encontrada no mês é procurada nos
outros meses fornecidos do ano. Se encontrada, a presença é confirmada e o caso
vai para Pendências para revisar a competência e os valores. A comparação avulsa
entre dois arquivos continua exigindo o mesmo período. Documentos sem chave não
são associados automaticamente entre meses.

### Como interpretar as saídas

A coluna **Presença EFD Contribuições** separa a localização do documento da
conferência de valores:

- `PRESENTE`: existe correspondência identificável, mesmo que haja divergência,
  duplicidade ou escrituração em outro período;
- `NAO_LOCALIZADA`: documento individual do ICMS sem correspondência nem evidência
  alternativa compatível nas formas de escrituração verificadas;
- `INCONCLUSIVA`: consolidação, dados insuficientes, identificação ambígua ou
  registro não mapeado impedem concluir;
- `SEM_ARQUIVO`: a EFD Contribuições correspondente não foi fornecida e a busca
  anual não encontrou uma chave em outro período.

Os status `CONFERENTE`, `DIVERGENTE`, `SOMENTE_EFD_CONTRIBUICOES`,
`SOMENTE_EFD_ICMS` e os três status de duplicidade continuam disponíveis.
`CONFERENTE` significa igualdade dos campos comuns aos dois leiautes, não
validação integral da nota. Há também `REVISAO_NECESSARIA`,
`SEM_EFD_CONTRIBUICOES` e `SEM_EFD_ICMS`.

Use as abas nesta ordem:

1. **Não lançadas**: documentos individuais classificados como `NAO_LOCALIZADA`,
   inclusive duplicados no ICMS. A situação fiscal e as quantidades são mantidas.
2. **Pendências**: casos sem conclusão automática, com motivo, arquivo, registro,
   linhas e evidências para conferência, além das chaves encontradas em outro mês.
3. **Cobertura**: registros encontrados em cada arquivo, quantidade, primeira
   linha e tratamento — documento individual, sem identificação individual,
   auxiliar ou não mapeado.

A coluna histórica `Chave NF-e` também contém as chaves dos demais documentos
eletrônicos; o modelo e o registro indicam o tipo.
`Chave EFD Contribuições` e `Chave EFD ICMS` preservam separadamente o que foi
informado em cada arquivo. `Quantidade EFD ICMS` e
`Quantidade EFD Contribuições` contam ocorrências da evidência daquela linha.
Linhas de resumo não representam uma nota individual e seus valores não devem
ser somados aos documentos detalhados como se fossem operações adicionais.

### Consolidações e limites da conferência

São sinalizados os resumos do ICMS B030/B350, C300/C405/C495/C600/C700/C860,
D300/D355/D400/D410/D600/D695/D750. Faixas de números não são expandidas em
notas fictícias. C465 complementa C460; itens, apurações e documentos apenas
referenciados, como C113 e D162, não são contados como outra nota.

Nas Contribuições, C180/C190/C380/C405/C490/C600/C860,
D200/D300/D350/D600 e F500/F510/F550/F560 podem impedir uma conclusão por nota.
F100 também é tratado como evidência sem identidade fiscal padronizada.
A compatibilidade considera estabelecimento, modelo, operação, datas, série,
equipamento e faixa numérica quando disponíveis. Ela gera uma pendência; não
comprova que uma nota específica integra o total. Campos ausentes tornam a
avaliação mais conservadora.

Códigos não mapeados nos blocos documentais são expostos em Cobertura e
Pendências; não desaparecem silenciosamente. Leiautes de documentos conhecidos
com quantidade de campos incompatível interrompem o processamento. A amostra
compacta original continua aceita para A100 e C100 das Contribuições.

**Não localizado não significa omissão fiscal comprovada.** A obrigatoriedade
de escriturar uma operação nas Contribuições depende de seu tratamento fiscal.
A conferência não substitui o PVA nem determina direito a crédito ou tributo devido.
Quando o TXT contém somente resumos, a validação individual exige documentos
adicionais, como XML ou relatórios do sistema de origem; estes não são importados
nesta versão. A ampliação documental não altera o escopo do conversor analítico
nem as regras dos indicadores descritas abaixo.

O arquivo `efd_icms_sintetico_estrutura_real.txt` é uma massa fictícia focada
em C100 e C190, não homologada pelo PVA. Nessa amostra, a chave exclusiva do
ICMS exige revisão por haver F550 compatível; ela não é tratada automaticamente
como não lançada. Os testes em `tests/test_document_scope.py` exercitam os
registros adicionais e as situações de cobertura.

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
- No conversor analítico, registros fora dos grupos operacionais definidos são
  ignorados. Na conferência documental, registros desconhecidos nos blocos
  documentais são explicitados como pendências.
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

O mapa da comparação ampliada foi conferido no [Guia Prático EFD ICMS/IPI
v3.2.3](https://www.gov.br/sped/pt-br/assuntos/escrituracoes-digitais/efd-icms-ipi/guia%20pratico)
e no Guia da EFD Contribuições v1.35 citado acima. As posições e os códigos
auxiliares estão concentrados em `src/efd_contribuicoes_csv/document_layouts.py`.
