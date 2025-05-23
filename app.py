from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import sqlite3
import os
from datetime import datetime
import unicodedata

app = Flask(__name__)
app.debug = True  # só em desenvolvimento!

# Caminhos
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(PROJECT_DIR, 'produtos.db')
REL_EXCEL   = os.path.join(PROJECT_DIR, 'produtos_bipados.xlsx')

# Inicializa o banco SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY,
            nome TEXT,
            codigo_interno TEXT,
            ean TEXT,
            fornecedor TEXT,
            quantidades INTEGER,
            bipado INTEGER,
            data_bipagem TEXT,
            localizacao TEXT,
            loja TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Normalização de cabeçalhos
def normalize(col):
    return unicodedata.normalize('NFKD', col).encode('ASCII','ignore').decode().lower().strip()

init_db()

@app.route('/', methods=['GET','POST'])
def index():
    mensagem = None

    if request.method == 'POST':
        acao = request.form.get('acao')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 1) Carregar Base
        if acao == 'carregar_base':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            modo    = request.form.get('modo','adicionar')
            if arquivo and arquivo.filename.lower().endswith('.xlsx'):
                df = pd.read_excel(arquivo)
                # normaliza colunas
                df.columns = [normalize(c) for c in df.columns]
                # garante as colunas que usamos
                df['fornecedor'] = df.get('fornecedor', '')
                if 'quantidades' in df.columns:
                    # converte para inteiro, preenchendo NaN com 0
                    df['quantidades'] = pd.to_numeric(df['quantidades'], errors='coerce').fillna(0).astype(int)
                else:
                    df['quantidades'] = 0
                df['bipado']        = 0
                df['data bipagem']  = ''
                df['local']         = ''
                df['loja']          = loja

                if modo == 'substituir':
                    c.execute('DELETE FROM produtos')
                for _, row in df.iterrows():
                    c.execute('''
                        INSERT OR IGNORE INTO produtos
                        (nome,codigo_interno,ean,fornecedor,quantidades,
                         bipado,data_bipagem,localizacao,loja)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    ''', (
                        row.get('nome',''),
                        row.get('codigo interno',''),
                        row.get('ean',''),
                        row.get('fornecedor',''),
                        int(row['quantidades']),
                        0, '', '', loja
                    ))
                conn.commit()
                mensagem = 'Base carregada com sucesso.'
            else:
                mensagem = 'Envie um .xlsx válido.'

        # 2) Importar Bipados
        elif acao == 'importar_bipados':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            local   = request.form.get('local','').strip()
            if arquivo and arquivo.filename.lower().endswith('.xlsx'):
                df = pd.read_excel(arquivo)
                df.columns = [normalize(c) for c in df.columns]
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                for _, row in df.iterrows():
                    codigo = row.get('ean','') or row.get('codigo interno','')
                    c.execute('''
                        UPDATE produtos
                        SET bipado=1, data_bipagem=?, localizacao=?
                        WHERE (ean=? OR codigo_interno=?)
                          AND (loja=? OR ?='')
                    ''', (now, local, codigo, codigo, loja, loja))
                conn.commit()
                mensagem = 'Bipados importados com sucesso.'
            else:
                mensagem = 'Envie um .xlsx válido.'

        # 3) Bipagem Manual
        elif acao == 'bipagem_manual':
            codigo = request.form.get('codigo_barras','').strip()
            loja   = request.form.get('loja','').strip()
            local  = request.form.get('local','').strip()
            now    = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''
                UPDATE produtos
                SET bipado=1, data_bipagem=?, localizacao=?
                WHERE (ean=? OR codigo_interno=?)
                  AND (loja=? OR ?='')
            ''', (now, local, codigo, codigo, loja, loja))
            conn.commit()
            mensagem = 'Produto bipado manualmente.' if c.rowcount else 'Produto não encontrado.'

        conn.close()

    return render_template('index.html', mensagem=mensagem)

@app.route('/data')
def data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    draw   = int(request.args.get('draw', 1))
    start  = int(request.args.get('start', 0))
    length = int(request.args.get('length', 10))
    search = request.args.get('search[value]', '').lower()

    c.execute('SELECT COUNT(*) FROM produtos')
    recordsTotal = c.fetchone()[0]

    if search:
        q = f"%{search}%"
        c.execute('''
            SELECT COUNT(*) FROM produtos
            WHERE lower(nome) LIKE ? OR lower(codigo_interno) LIKE ?
               OR lower(ean) LIKE ? OR lower(fornecedor) LIKE ?
        ''', (q,q,q,q))
        recordsFiltered = c.fetchone()[0]
        c.execute('''
            SELECT nome, codigo_interno, ean, fornecedor, quantidades,
                   bipado, data_bipagem, localizacao
            FROM produtos
            WHERE lower(nome) LIKE ? OR lower(codigo_interno) LIKE ?
               OR lower(ean) LIKE ? OR lower(fornecedor) LIKE ?
            LIMIT ? OFFSET ?
        ''', (q,q,q,q, length, start))
    else:
        recordsFiltered = recordsTotal
        c.execute('''
            SELECT nome, codigo_interno, ean, fornecedor, quantidades,
                   bipado, data_bipagem, localizacao
            FROM produtos
            LIMIT ? OFFSET ?
        ''', (length, start))

    cols = [col[0] for col in c.description]
    data = [dict(zip(cols, row)) for row in c.fetchall()]
    conn.close()

    return jsonify({
        'draw': draw,
        'recordsTotal': recordsTotal,
        'recordsFiltered': recordsFiltered,
        'data': data
    })

@app.route('/download')
def download_excel():
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql('SELECT * FROM produtos', conn)
    conn.close()
    df.to_excel(REL_EXCEL, index=False)
    return send_file(REL_EXCEL, as_attachment=True)

if __name__ == '__main__':
    app.run()
