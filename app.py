import os
import pandas as pd
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import unicodedata

# --- Configuração do Flask e do Banco ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')  # do Render env var
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# URL do CSV público do Google Sheet (configure em Environment Variables)
SHEET_CSV_URL = os.getenv('SHEET_CSV_URL')

# --- Modelo ORM ---
class Produto(db.Model):
    __tablename__ = 'produtos'
    id             = db.Column(db.Integer, primary_key=True)
    nome           = db.Column(db.String, nullable=False)
    codigo_interno = db.Column(db.String, nullable=False)
    ean            = db.Column(db.String, nullable=False)
    fornecedor     = db.Column(db.String, default='')
    quantidades    = db.Column(db.Integer, default=0)
    bipado         = db.Column(db.Boolean, default=False)
    data_bipagem   = db.Column(db.DateTime)
    localizacao    = db.Column(db.String, default='')
    loja           = db.Column(db.String, default='')
    __table_args__ = (
        db.UniqueConstraint('codigo_interno', 'ean', name='uq_produto_codigo_ean'),
    )

with app.app_context():
    db.create_all()

# --- Helpers ---
def normalize(col: str) -> str:
    return unicodedata.normalize('NFKD', col).encode('ASCII','ignore').decode().lower().strip()

def generate_csv(rows):
    cols = ['nome','codigo_interno','ean','fornecedor','quantidades','bipado','data_bipagem','localizacao','loja']
    yield ','.join(cols) + '\n'
    for row in rows:
        vals = []
        for c in cols:
            v = getattr(row, c)
            if v is None:
                vals.append('')
            else:
                text = v.strftime('%d/%m/%Y %H:%M') if isinstance(v, datetime) else str(v)
                vals.append(f'"{text.replace("\"","\"\"')}"')
        yield ','.join(vals) + '\n'

# --- Rotas ---
@app.route('/', methods=['GET','POST'])
def index():
    mensagem = None
    if request.method == 'POST':
        acao = request.form['acao']
        loja = request.form.get('loja','').strip()
        local = request.form.get('local','').strip()

        # 1) Carregar Base a partir do Google Sheets CSV
        if acao == 'carregar_base':
            if not SHEET_CSV_URL:
                mensagem = 'SHEET_CSV_URL não configurada.'
            else:
                df = pd.read_csv(SHEET_CSV_URL)
                df.columns = [normalize(c) for c in df.columns]
                df['loja'] = loja
                if 'quantidades' in df.columns:
                    df['quantidades'] = pd.to_numeric(df['quantidades'], errors='coerce').fillna(0).astype(int)
                else:
                    df['quantidades'] = 0
                df['fornecedor'] = df.get('fornecedor','')
                df['bipado'] = False
                df['data_bipagem'] = ''
                df['localizacao'] = ''
                df = df.drop_duplicates(subset=['codigo interno','ean'])
                now = datetime.now()
                for _, row in df.iterrows():
                    prod = Produto(
                        nome=row.get('nome',''),
                        codigo_interno=str(row.get('codigo interno','')),
                        ean=str(row.get('ean','')),
                        fornecedor=row['fornecedor'],
                        quantidades=int(row['quantidades']),
                        bipado=False,
                        loja=loja
                    )
                    try:
                        db.session.add(prod)
                        db.session.commit()
                    except:
                        db.session.rollback()
                mensagem = 'Base carregada do Google Sheets com sucesso.'

        # 2) Importar Bipados via CSV do Form
        elif acao == 'importar_bipados':
            f = request.files.get('file')
            if f and f.filename.lower().endswith('.xlsx'):
                df = pd.read_excel(f)
                df.columns = [normalize(c) for c in df.columns]
                now = datetime.now()
                for _, row in df.iterrows():
                    cod = str(row.get('ean','') or row.get('codigo interno','')).strip()
                    prod = Produto.query.filter(
                        ((Produto.ean==cod)|(Produto.codigo_interno==cod)),
                        ((Produto.loja==loja)|(loja==''))
                    ).first()
                    if prod:
                        prod.bipado = True
                        prod.data_bipagem = now
                        prod.localizacao = local
                db.session.commit()
                mensagem = 'Bipados importados com sucesso.'
            else:
                mensagem = 'Envie um .xlsx válido.'

        # 3) Bipagem Manual
        elif acao == 'bipagem_manual':
            cod = request.form.get('codigo_barras','').strip()
            now = datetime.now()
            prod = Produto.query.filter(
                ((Produto.ean==cod)|(Produto.codigo_interno==cod)),
                ((Produto.loja==loja)|(loja==''))
            ).first()
            if prod:
                prod.bipado = True
                prod.data_bipagem = now
                prod.localizacao = local
                db.session.commit()
                mensagem = 'Produto bipado manualmente.'
            else:
                mensagem = 'Produto não encontrado.'

    return render_template('index.html', mensagem=mensagem)

@app.route('/data')
def data():
    draw = int(request.args.get('draw',1))
    start = int(request.args.get('start',0))
    length = int(request.args.get('length',10))
    search = request.args.get('search[value]','').lower()

    query = Produto.query
    total = query.count()
    if search:
        like = f"%{search}%"
        query = query.filter(
            Produto.nome.ilike(like) | Produto.codigo_interno.ilike(like)
        )
    filtered = query.count()
    rows = query.order_by(Produto.id).offset(start).limit(length).all()

    data = [{
        'nome': p.nome,
        'codigo_interno': p.codigo_interno,
        'ean': p.ean,
        'fornecedor': p.fornecedor,
        'quantidades': p.quantidades,
        'bipado': p.bipado,
        'data_bipagem': p.data_bipagem.strftime('%d/%m/%Y %H:%M') if p.data_bipagem else '',
        'localizacao': p.localizacao
    } for p in rows]

    return jsonify({ 'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data })

# Downloads CSV
@app.route('/download_csv')
def dl_all():
    rows = Produto.query.all()
    return Response(stream_with_context(generate_csv(rows)), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=produtos.csv'})

@app.route('/download_csv_bipados')
def dl_bipados():
    rows = Produto.query.filter_by(bipado=True).all()
    return Response(stream_with_context(generate_csv(rows)), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=bipados.csv'})

@app.route('/download_csv_nao_bipados')
def dl_nao_bipados():
    rows = Produto.query.filter_by(bipado=False).all()
    return Response(stream_with_context(generate_csv(rows)), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=nao_bipados.csv'})

if __name__ == '__main__':
    app.run(debug=True)