from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import os
from datetime import datetime
import unicodedata
import io

app = Flask(__name__)
base_dados = pd.DataFrame()

def normalize(col):
    return unicodedata.normalize('NFKD', col).encode('ASCII','ignore').decode().lower().strip()

PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))
REL_EXCEL      = os.path.join(PROJECT_DIR, "produtos_bipados.xlsx")

def salvar_base():
    if not base_dados.empty:
        base_dados.to_excel(REL_EXCEL, index=False)

@app.route('/', methods=['GET','POST'])
def index():
    global base_dados
    mensagem = None

    if request.method == 'POST':
        acao = request.form.get('acao')

        # carregar base
        if acao == 'carregar_base':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            modo    = request.form.get('modo','adicionar')
            if arquivo and arquivo.filename.lower().endswith('.xlsx'):
                df = pd.read_excel(arquivo)
                df.columns = [normalize(c) for c in df.columns]
                df['loja'] = loja
                for col in ['bipado','data bipagem','local']:
                    if col not in df.columns:
                        df[col] = False if col=='bipado' else ''
                if modo == 'substituir':
                    base_dados = df
                    mensagem = 'Base substituída com sucesso.'
                else:
                    if base_dados.empty:
                        base_dados = df
                    else:
                        comb = pd.concat([base_dados, df], ignore_index=True)
                        base_dados = comb.drop_duplicates(subset=['codigo interno','ean'], keep='first')
                    mensagem = 'Produtos adicionados à base.'
                salvar_base()
            else:
                mensagem = 'Envie um .xlsx válido.'

        # importar bipados
        elif acao == 'importar_bipados':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            local   = request.form.get('local','').strip()
            if not base_dados.empty and arquivo and arquivo.filename.lower().endswith('.xlsx'):
                bip = pd.read_excel(arquivo)
                bip.columns = [normalize(c) for c in bip.columns]
                for _, item in bip.iterrows():
                    ean     = str(item.get('ean','')).strip()
                    interno = str(item.get('codigo interno','')).strip()
                    mask = ((base_dados['ean'].astype(str)==ean) |
                            (base_dados['codigo interno'].astype(str)==interno))
                    if loja:
                        mask &= (base_dados['loja']==loja)
                    if mask.any():
                        base_dados.loc[mask,'bipado'] = True
                        base_dados.loc[mask,'data bipagem'] = datetime.now().strftime('%d/%m/%Y %H:%M')
                        base_dados.loc[mask,'local'] = local
                mensagem = 'Produtos atualizados com sucesso.'
                salvar_base()
            else:
                mensagem = 'Carregue a base e envie um .xlsx válido de bipados.'

        # bipagem manual
        elif acao == 'bipagem_manual':
            codigo = request.form.get('codigo_barras','').strip()
            loja   = request.form.get('loja','').strip()
            local  = request.form.get('local','').strip()
            if not base_dados.empty and codigo:
                mask = ((base_dados['ean'].astype(str)==codigo) |
                        (base_dados['codigo interno'].astype(str)==codigo))
                if loja:
                    mask &= (base_dados['loja']==loja)
                if mask.any():
                    base_dados.loc[mask,'bipado'] = True
                    base_dados.loc[mask,'data bipagem'] = datetime.now().strftime('%d/%m/%Y %H:%M')
                    base_dados.loc[mask,'local'] = local
                    mensagem = 'Produto bipado manualmente.'
                else:
                    mensagem = 'Produto não encontrado.'
                salvar_base()
            else:
                mensagem = 'Carregue a base primeiro ou informe o código.'

    return render_template('index.html', mensagem=mensagem)

@app.route('/data')
def data():
    """Endpoint JSON para DataTables server-side."""
    global base_dados
    df = base_dados.copy()
    draw = int(request.args.get('draw', 1))
    start = int(request.args.get('start', 0))
    length = int(request.args.get('length', 10))
    search_value = request.args.get('search[value]', '').lower()

    # filtragem
    if search_value:
        mask = df.apply(lambda row: row.astype(str).str.lower().str.contains(search_value).any(), axis=1)
        df = df[mask]

    recordsTotal = len(base_dados)
    recordsFiltered = len(df)

    # paginação
    page = df.iloc[start:start+length]

    data = page.fillna('').to_dict(orient='records')
    # mantém a ordem das colunas conforme o header de HTML
    return jsonify({
        'draw': draw,
        'recordsTotal': recordsTotal,
        'recordsFiltered': recordsFiltered,
        'data': data
    })

@app.route('/download')
def download_excel():
    if os.path.exists(REL_EXCEL):
        return send_file(REL_EXCEL, as_attachment=True)
    return 'Nenhum relatório.', 404

if __name__ == '__main__':
    app.run(debug=True)
