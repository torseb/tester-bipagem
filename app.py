from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import sqlite3, os, unicodedata
from datetime import datetime
import pandas as pd

app = Flask(__name__)
DB_PATH = os.path.join(os.getcwd(), 'produtos.db')

# Inicializa DB

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
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
                loja TEXT,
                UNIQUE(codigo_interno, ean)
            )
        ''')
init_db()

# Normaliza cabeçalhos

def normalize(col):
    return unicodedata.normalize('NFKD', col).encode('ASCII','ignore').decode().lower().strip()

# Gera CSV em streaming

def generate_csv(df):
    yield ','.join(df.columns) + '\n'
    for row in df.itertuples(index=False):
        vals = ['"%s"' % str(v).replace('"','""') for v in row]
        yield ','.join(vals) + '\n'

@app.route('/', methods=['GET','POST'])
def index():
    mensagem = None
    if request.method == 'POST':
        acao = request.form['acao']
        loja = request.form.get('loja','').strip()
        local = request.form.get('local','').strip()
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # 1. Carregar base
            if acao == 'carregar_base':
                f = request.files.get('file')
                if f and f.filename.lower().endswith('.xlsx'):
                    df = pd.read_excel(f)
                    df.columns = [normalize(c) for c in df.columns]
                    df['loja'] = loja
                    df['quantidades'] = pd.to_numeric(df.get('quantidades',0), errors='coerce').fillna(0).astype(int)
                    df['fornecedor'] = df.get('fornecedor','')
                    df['bipado'] = 0
                    df['data_bipagem'] = ''
                    df['localizacao'] = ''
                    for _, row in df.drop_duplicates(subset=['codigo interno','ean']).iterrows():
                        c.execute('''INSERT OR IGNORE INTO produtos
                            (nome, codigo_interno, ean, fornecedor, quantidades, bipado, data_bipagem, localizacao, loja)
                            VALUES (?,?,?,?,?,?,?,?,?)''', (
                            row.get('nome',''), row.get('codigo interno',''), row.get('ean',''),
                            row['fornecedor'], int(row['quantidades']), 0, '', '', loja
                        ))
                    mensagem = 'Base carregada com sucesso.'
                else:
                    mensagem = 'Envie um arquivo .xlsx válido.'

            # 2. Importar bipados
            elif acao == 'importar_bipados':
                f = request.files.get('file')
                if f and f.filename.lower().endswith('.xlsx'):
                    bip = pd.read_excel(f)
                    bip.columns = [normalize(c) for c in bip.columns]
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    for _, r in bip.iterrows():
                        cod = str(r.get('ean','') or r.get('codigo interno','')).strip()
                        c.execute('''UPDATE produtos SET bipado=1, data_bipagem=?, localizacao=?
                                     WHERE (ean=? OR codigo_interno=?)
                                     AND (loja=? OR ?='')''', (now, local, cod, cod, loja, loja))
                    mensagem = 'Bipados importados com sucesso.'
                else:
                    mensagem = 'Envie um arquivo .xlsx válido.'

            # 3. Bipagem manual
            elif acao == 'bipagem_manual':
                cod = request.form.get('codigo_barras','').strip()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                c.execute('''UPDATE produtos SET bipado=1, data_bipagem=?, localizacao=?
                             WHERE (ean=? OR codigo_interno=?)
                             AND (loja=? OR ?='')''', (now, local, cod, cod, loja, loja))
                mensagem = 'Produto bipado manualmente.' if c.rowcount else 'Produto não encontrado.'

    return render_template('index.html', mensagem=mensagem)

@app.route('/data')
def data():
    draw = int(request.args.get('draw', 1))
    start = int(request.args.get('start', 0))
    length = int(request.args.get('length', 10))
    search = request.args.get('search[value]', '').lower()
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM produtos')
        total = c.fetchone()[0]
        if search:
            like = f"%{search}%"
            c.execute('SELECT COUNT(*) FROM produtos WHERE lower(nome) LIKE ? OR lower(codigo_interno) LIKE ?', (like,like))
            filt = c.fetchone()[0]
            c.execute('''SELECT nome, codigo_interno, ean, fornecedor, quantidades, bipado, data_bipagem, localizacao
                         FROM produtos WHERE lower(nome) LIKE ? OR lower(codigo_interno) LIKE ? LIMIT ? OFFSET ?''', (like,like,length,start))
        else:
            filt = total
            c.execute('''SELECT nome, codigo_interno, ean, fornecedor, quantidades, bipado, data_bipagem, localizacao
                         FROM produtos LIMIT ? OFFSET ?''', (length, start))
        cols = [d[0] for d in c.description]
        data = [dict(zip(cols,row)) for row in c.fetchall()]
    return jsonify({'draw':draw,'recordsTotal':total,'recordsFiltered':filt,'data':data})

# Downloads CSV:
@app.route('/download_csv')
def dl_all():
    df = pd.read_sql('SELECT * FROM produtos', sqlite3.connect(DB_PATH))
    return Response(stream_with_context(generate_csv(df)), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=produtos.csv'})

@app.route('/download_csv_bipados')
def dl_bipados():
    df = pd.read_sql('SELECT * FROM produtos WHERE bipado=1', sqlite3.connect(DB_PATH))
    return Response(stream_with_context(generate_csv(df)), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=bipados.csv'})

@app.route('/download_csv_nao_bipados')
def dl_nao_bipados():
    df = pd.read_sql('SELECT * FROM produtos WHERE bipado=0', sqlite3.connect(DB_PATH))
    return Response(stream_with_context(generate_csv(df)), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=nao_bipados.csv'})

if __name__ == '__main__':
    app.run(debug=True)