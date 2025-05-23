# app.py
from flask import Flask, render_template, request, send_file
import pandas as pd
import os
from datetime import datetime
import unicodedata

app = Flask(__name__)
base_dados = pd.DataFrame()

def normalize(col):
    return unicodedata.normalize('NFKD', col).encode('ASCII','ignore').decode().lower().strip()

PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))
RELATORIO_PATH = os.path.join(PROJECT_DIR, "produtos_bipados.xlsx")

def salvar_base():
    if not base_dados.empty:
        base_dados.to_excel(RELATORIO_PATH, index=False)

@app.route('/', methods=['GET','POST'])
def index():
    global base_dados
    mensagem = None

    if request.method == 'POST':
        acao = request.form.get('acao')

        # 1) carregar base
        if acao == 'carregar_base':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            modo    = request.form.get('modo','adicionar')
            if arquivo and arquivo.filename.endswith('.xlsx'):
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
                        comb = pd.concat([base_dados,df], ignore_index=True)
                        base_dados = comb.drop_duplicates(subset=['codigo interno','ean'], keep='first')
                    mensagem = 'Produtos adicionados à base.'
                salvar_base()
            else:
                mensagem = 'Envie um .xlsx válido.'

        # 2) importar bipados via arquivo
        elif acao == 'importar_bipados':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            local   = request.form.get('local','').strip()
            if not base_dados.empty and arquivo and arquivo.filename.endswith('.xlsx'):
                bip = pd.read_excel(arquivo)
                bip.columns = [normalize(c) for c in bip.columns]
                for _,item in bip.iterrows():
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

        # 3) bipagem manual
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

    produtos = base_dados.to_dict(orient='records') if not base_dados.empty else []
    return render_template('index.html', produtos=produtos, mensagem=mensagem)

@app.route('/download')
def download():
    if os.path.exists(RELATORIO_PATH):
        return send_file(RELATORIO_PATH, as_attachment=True)
    return 'Relatório não encontrado.', 404

if __name__ == '__main__':
    app.run(debug=True)
