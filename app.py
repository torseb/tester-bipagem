from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import sqlite3
import os
from datetime import datetime
import unicodedata

app = Flask(__name__)

# Caminhos
PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH        = os.path.join(PROJECT_DIR, 'produtos.db')
REL_EXCEL      = os.path.join(PROJECT_DIR, 'produtos_bipados.xlsx')

# Inicializa o banco (tabela produtos vazia, se não existir)
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

# Normalização de colunas
def normalize(col):
    return unicodedata.normalize('NFKD', col).encode('ASCII','ignore').decode().lower().strip()

init_db()

@app.route('/', methods=['GET','POST'])
def index():
    mensagem = None
    if request.method == 'POST':
        acao = request.form.get('acao')
        # Conexão
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 1) carregar base
        if acao == 'carregar_base':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            modo    = request.form.get('modo','adicionar')
            if arquivo and arquivo.filename.lower().endswith('.xlsx'):
                df = pd.read_excel(arquivo)
                df.columns = [normalize(c) for c in df.columns]
                df['fornecedor']    = df.get('fornecedor','')
                df['quantidades']   = df.get('quantidades',0).astype(int)
                df['bipado']        = 0
                df['data bipagem']  = ''
                df['local']         = ''
                df['loja']          = loja

                if modo == 'substituir':
                    c.execute('DELETE FROM produtos')
                # Insertando tudo
                for _, row in df.iterrows():
                    c.execute('''
                        INSERT OR IGNORE INTO produtos
                        (nome, codigo_interno, ean, fornecedor, quantidades,
                         bipado, data_bipagem, localizacao, loja)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row.get('nome',''),
                        row.get('codigo interno',''),
                        row.get('ean',''),
                        row.get('fornecedor',''),
                        int(row.get('quantidades',0)),
                        0, '', '', loja
                    ))
                conn.commit()
                mensagem = 'Base carregada com sucesso.'
            else:
                mensagem = 'Envie um .xlsx válido.'

        # 2) importar bipados
        elif acao == 'importar_bipados':
            arquivo = request.files.get('file')
            loja    = request.form.get('loja','').strip()
            local   = request.form.get('local','').strip()
            if arquivo and arquivo.filename.lower().endswith('.xlsx'):
                df = pd.read_excel(arquivo)
                df.columns = [normalize(c) for c in df.columns]
                for _, row in df.iterrows():
                    código = row.get('ean','') or row.get('codigo interno','')
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    c.execute('''
                        UPDATE produtos
                        SET bipado=1, data_bipagem=?, localizacao=?
                        WHERE (ean=? OR codigo_interno=?)
                          AND (loja=? OR ?='')
                    ''', (now, local, código, código, loja, loja))
                conn.commit()
                mensagem = 'Bipados importados com sucesso.'
            else:
                mensagem = 'Envie um .xlsx válido.'

        # 3) bipagem manual
        elif acao == 'bipagem_manual':
            código = request.form.get('codigo_barras','').strip()
            loja   = request.form.get('loja','').strip()
            local  = request.form.get('local','').strip()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''
                UPDATE produtos
                SET bipado=1, data_bipagem=?, localizacao=?
                WHERE (ean=? OR codigo_interno=?)
                  AND (loja=? OR ?='')
            ''', (now, local, código, código, loja, loja))
            if c.rowcount:
                mensagem = 'Produto bipado manualmente.'
            else:
                mensagem = 'Produto não encontrado.'
            conn.commit()

        conn.close()

    return render_template('index.html', mensagem=mensagem)

@app.route('/data')
def data():
    """DataTables server-side endpoint."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # parâmetros DataTables
    draw = int(request.args.get('draw', '1'))
    start = int(request.args.get('start', '0'))
    length = int(request.args.get('length', '10'))
    search = request.args.get('search[value]', '').lower()

    # contagem total
    c.execute('SELECT COUNT(*) FROM produtos')
    recordsTotal = c.fetchone()[0]

    # busca
    if search:
        q = f"%{search}%"
        c.execute(f'''
            SELECT COUNT(*) FROM produtos
            WHERE lower(nome) LIKE ? OR lower(codigo_interno) LIKE ?
               OR lower(ean) LIKE ? OR lower(fornecedor) LIKE ?
        ''', (q,q,q,q))
        recordsFiltered = c.fetchone()[0]

        c.execute(f'''
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

    data = [dict(zip([column[0] for column in c.description], row)) for row in c.fetchall()]
    conn.close()

    return jsonify({
        'draw': draw,
        'recordsTotal': recordsTotal,
        'recordsFiltered': recordsFiltered,
        'data': data
    })

@app.route('/download')
def download_excel():
    # gera Excel rápido apenas da view completa (pode estourar memória se 30k)
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql('SELECT * FROM produtos', conn)
    conn.close()
    df.to_excel(REL_EXCEL, index=False)
    return send_file(REL_EXCEL, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
