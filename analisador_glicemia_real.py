# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# Aplicativo Web Dinâmico para Análise Glicêmica e Cálculo de Insulina
#
# Autor: Seu Especialista em IA
# Descrição: Este aplicativo Flask permite o upload de um relatório .mhtml,
#            extrai os dados e gera uma página de relatório interativa.
#            -- MODIFICADO para incluir um botão de download do relatório HTML. --
#
# Como usar:
# 1. Instale as dependências: pip install Flask beautifulsoup4
# 2. Execute este script: python analisador_glicemia_real.py
# 3. Abra seu navegador e acesse: http://127.0.0.1:5000
# -----------------------------------------------------------------------------

from flask import Flask, render_template_string, request, redirect, url_for, flash
import statistics
import re
from bs4 import BeautifulSoup
import quopri
import email
from email.message import Message
import json

app = Flask(__name__)
app.secret_key = 'super-secret-key' # Necessário para usar flash messages

# --- Módulo de Cálculo de Insulina ---
def get_default_correction_table():
    return {
        "101-135": 1, "136-170": 2, "171-205": 3, "206-240": 4,
        "241-275": 5, "276-310": 6, "311-345": 7, "345+": 8
    }

def calcular_dose_correcao(glicemia, correction_table):
    """Calcula a dose de correção de insulina com base na glicemia e na tabela de correção."""
    if glicemia < 101: return 0
    
    for range_str, dose in correction_table.items():
        if '+' in range_str:
            limit = int(range_str.replace('+', ''))
            if glicemia > limit:
                return int(dose)
        else:
            low, high = map(int, range_str.split('-'))
            if low <= glicemia <= high:
                return int(dose)
    return 0 # Fallback

def calcular_dose_insulina(glicemia, carbs=0.0, tipo_medicao="", carb_ratio=15, correction_table=None):
    """
    Calcula a dose total de insulina Lispro.
    """
    if correction_table is None:
        correction_table = get_default_correction_table()

    dose_carboidratos = 0
    if 'antes' in tipo_medicao.lower() and carbs > 0 and carb_ratio > 0:
        dose_carboidratos = round(carbs / carb_ratio)

    dose_correcao = calcular_dose_correcao(glicemia['valor'], correction_table)
    
    if 'depois' in tipo_medicao.lower():
        glicemia['dose_sugerida'] = dose_correcao
        glicemia['calculo'] = f"Correção para {glicemia['valor']}mg/dL = {dose_correcao}UI"
    else:
        glicemia['dose_sugerida'] = dose_carboidratos + dose_correcao
        glicemia['calculo'] = f"Carbs ({carbs}g / {carb_ratio} = {dose_carboidratos}UI) + Correção ({glicemia['valor']}mg/dL = {dose_correcao}UI) = {glicemia['dose_sugerida']}UI"
    
    return glicemia

# --- Módulo de Extração e Processamento de Dados ---
def parse_mhtml(file_storage, patient_name, carb_ratio, correction_table):
    """
    Extrai o conteúdo HTML de um arquivo MHTML e o processa com BeautifulSoup.
    """
    try:
        msg = email.message_from_bytes(file_storage.read())
        html_part = next((part for part in msg.walk() if part.get_content_type() == "text/html"), None)
        
        if not html_part:
            return None, "Não foi possível encontrar o conteúdo HTML no arquivo."

        charset = html_part.get_content_charset() or 'utf-8'
        html_content_quoted = html_part.get_payload(decode=False)
        html_content_bytes = quopri.decodestring(html_content_quoted)
        html = html_content_bytes.decode(charset)
        soup = BeautifulSoup(html, 'html.parser')
        
        dados = {
            "paciente": patient_name,
            "periodo": soup.find('h2').text.replace('Relatório: ', ''),
            "dias": []
        }
        
        dias_html = soup.find_all('h1', class_='font-bold text-xl')
        
        for dia_h1 in dias_html:
            dia_container = dia_h1.parent
            dia_data = {"data": dia_h1.text, "total_kcal": 0, "total_carbs": 0, "glicemias": [], "refeicoes": []}
            
            p_total = dia_h1.find_next_sibling('p')
            if p_total and (match := re.search(r'([\d\.]+) kcals / ([\d\.]+) carbs', p_total.text)):
                dia_data["total_kcal"], dia_data["total_carbs"] = map(float, match.groups())

            cards = dia_container.find_next_siblings('div', class_='rounded')
            for card in cards:
                if not (card_title_element := card.find('div', class_='font-bold text-lg')): continue
                card_title = card_title_element.text.strip()
                
                if card_title == 'Glicemias':
                    for p in card.find_all('p', class_='text-gray-500'):
                        if (tipo_element := p.find_previous_sibling('p')) and (match := re.search(r'(\d{2}:\d{2}): (\d+) mg/dl', p.text)):
                            dia_data['glicemias'].append({"hora": match.group(1), "valor": int(match.group(2)), "tipo": tipo_element.text.strip()})
                else:
                    refeicao = {"nome": card_title, "total_kcal": 0, "total_carbs": 0, "alimentos": []}
                    if (details_div := card.find('div', class_='text-sm text-gray-500')) and (match := re.search(r'([\d\.]+) kcals / ([\d\.]+) carbs', details_div.text)):
                        refeicao['total_kcal'], refeicao['total_carbs'] = map(float, match.groups())
                    
                    for alimento_p in card.select('.p-4 > div > div > p.font-bold'):
                        nome_alimento = alimento_p.text
                        detalhes_div = alimento_p.find_next_sibling('div')
                        if detalhes_div:
                            refeicao['alimentos'].append({"nome": nome_alimento, "detalhes": " ".join(detalhes_div.stripped_strings)})
                    
                    dia_data['refeicoes'].append(refeicao)
            
            total_insulina_dia = 0
            for glicemia in dia_data['glicemias']:
                tipo_medicao = glicemia.get('tipo', '').lower()
                carbs_refeicao = 0
                if 'antes do café' in tipo_medicao:
                    refeicao_alvo = next((r for r in dia_data['refeicoes'] if r['nome'] == 'Café da manhã'), None)
                elif 'antes do almoço' in tipo_medicao:
                    refeicao_alvo = next((r for r in dia_data['refeicoes'] if r['nome'] == 'Almoço'), None)
                elif 'antes do jantar' in tipo_medicao:
                    refeicao_alvo = next((r for r in dia_data['refeicoes'] if r['nome'] == 'Jantar'), None)
                elif 'antes do lanche' in tipo_medicao:
                    refeicao_alvo = next((r for r in dia_data['refeicoes'] if 'Lanche' in r['nome']), None)
                else:
                    refeicao_alvo = None
                
                if refeicao_alvo:
                    carbs_refeicao = refeicao_alvo['total_carbs']
                
                calcular_dose_insulina(glicemia, carbs_refeicao, tipo_medicao, carb_ratio, correction_table)
                total_insulina_dia += glicemia.get('dose_sugerida', 0)
            
            dia_data['total_insulina'] = total_insulina_dia
            dados['dias'].append(dia_data)
        
        dados['total_dias'] = len(dados['dias'])
        return dados, None
    except Exception as e:
        return None, f"Ocorreu um erro ao processar o arquivo. Verifique se o formato está correto. Detalhe: {str(e)}"

def analisar_dados_gerais(dados_completos):
    todas_as_glicemias = [g['valor'] for dia in dados_completos.get('dias', []) for g in dia.get('glicemias', [])]
    if not todas_as_glicemias: return {}
    total = len(todas_as_glicemias)
    glicemia_media = statistics.mean(todas_as_glicemias)
    return {
        "glicemia_media": round(glicemia_media),
        "glicemia_max": max(todas_as_glicemias),
        "glicemia_min": min(todas_as_glicemias),
        "desvio_padrao": round(statistics.stdev(todas_as_glicemias), 1) if total > 1 else 0,
        "hba1c_estimada": round((glicemia_media + 46.7) / 28.7, 1),
        "tempo_no_alvo": {
            "no_alvo": round(sum(1 for g in todas_as_glicemias if 70 <= g <= 180) / total * 100),
            "abaixo": round(sum(1 for g in todas_as_glicemias if g < 70) / total * 100),
            "acima": round(sum(1 for g in todas_as_glicemias if g > 180) / total * 100)
        }
    }

# --- Rota Principal e Templates ---
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        if 'report_file' not in request.files or not request.files['report_file'].filename:
            flash('Nenhum arquivo selecionado.', 'error')
            return redirect(request.url)
        
        file = request.files['report_file']
        patient_name = request.form.get('patient_name') or "Utilizador"
        carb_ratio = float(request.form.get('carb_ratio', 15))
        correction_table = {key.replace('correction_', ''): val for key, val in request.form.items() if key.startswith('correction_')}

        if file.filename.endswith('.mhtml'):
            dados, erro = parse_mhtml(file, patient_name, carb_ratio, correction_table)
            if erro:
                flash(erro, 'error')
                return redirect(request.url)
            
            analise = analisar_dados_gerais(dados)
            
            chart_labels = []
            chart_data_points = []
            for dia in dados.get('dias', []):
                for g in dia.get('glicemias', []):
                    dia_label = dia['data'].split(' de ')[0]
                    chart_labels.append(f"{dia_label} {g['hora']}")
                    chart_data_points.append(g['valor'])

            chart_data = { "labels": chart_labels, "data": chart_data_points }

            # ### ALTERAÇÃO ### 
            # Cria o nome do arquivo, mas não o salva no servidor.
            # Apenas passa o nome para o template para que o JavaScript possa usá-lo.
            paciente_safe = re.sub(r'[^a-z0-9_]', '', patient_name.lower().replace(' ', '_'))
            periodo_safe = dados.get("periodo", "periodo").replace(' a ', '_').replace('/', '-')
            filename_html = f"relatorio_glicemico_{paciente_safe}_{periodo_safe}.html"

            return render_template_string(
                REPORT_TEMPLATE, 
                dados=dados, 
                analise=analise, 
                chart_data=json.dumps(chart_data), 
                calc_params={'ratio': carb_ratio, 'table': correction_table},
                filename_html=filename_html # Passa o nome do arquivo para o template
            )
        else:
            flash('Formato de arquivo inválido. Por favor, envie um arquivo .mhtml.', 'error')
            return redirect(request.url)

    return render_template_string(UPLOAD_TEMPLATE, correction_table=get_default_correction_table())

UPLOAD_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analisador de Glicemia</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen py-12">
    <div class="max-w-3xl w-full bg-white p-8 rounded-lg shadow-lg">
        <div class="text-center mb-8">
            <h1 class="text-3xl font-bold text-blue-700 mb-2">Analisador de Glicemia e Insulina</h1>
            <p class="text-gray-600">Configure os parâmetros de cálculo e carregue seu relatório (.mhtml).</p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
                    <strong class="font-bold">Erro:</strong>
                    <span class="block sm:inline">{{ message }}</span>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form action="/" method="post" enctype="multipart/form-data" class="space-y-8">
            <fieldset class="border rounded-lg p-4">
                <legend class="text-lg font-medium text-gray-800 px-2">Parâmetros de Cálculo</legend>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                    <div>
                        <label for="patient_name" class="block text-sm font-medium text-gray-700">Nome do Paciente</label>
                        <input type="text" name="patient_name" id="patient_name" class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm" placeholder="Opcional">
                    </div>
                    <div>
                        <label for="carb_ratio" class="block text-sm font-medium text-gray-700">Relação Insulina/Carboidrato (1 UI para Xg)</label>
                        <input type="number" name="carb_ratio" id="carb_ratio" value="15" class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm">
                    </div>
                </div>
                <div class="mt-6">
                    <h3 class="text-md font-medium text-gray-800 mb-2">Fator de Correção (UI adicional)</h3>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        {% for range, dose in correction_table.items() %}
                        <div>
                            <label for="correction_{{range}}" class="block text-xs font-medium text-gray-500">GC {{range}}</label>
                            <input type="number" name="correction_{{range}}" id="correction_{{range}}" value="{{dose}}" class="mt-1 block w-full px-2 py-1.5 bg-white border border-gray-300 rounded-md shadow-sm">
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </fieldset>

            <fieldset class="border rounded-lg p-4">
                <legend class="text-lg font-medium text-gray-800 px-2">Arquivo do Relatório</legend>
                <label for="report_file" class="relative block w-full mt-4 text-sm text-gray-700 bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:bg-gray-100 p-6 text-center">
                    <span id="file-upload-text" class="text-blue-600 font-semibold">Clique para carregar ou arraste o arquivo .mhtml aqui</span>
                    <input type="file" name="report_file" id="report_file" class="hidden" accept=".mhtml" required>
                </label>
            </fieldset>
            
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors text-lg">
                Analisar Relatório
            </button>
        </form>
    </div>
    <script>
        document.getElementById('report_file').addEventListener('change', function() {
            const textEl = document.getElementById('file-upload-text');
            if (this.files && this.files.length > 0) {
                textEl.textContent = `Arquivo: ${this.files[0].name}`;
                textEl.classList.replace('text-blue-600', 'text-green-600');
            } else {
                textEl.textContent = 'Clique para carregar ou arraste o arquivo .mhtml aqui';
                textEl.classList.replace('text-green-600', 'text-blue-600');
            }
        });
    </script>
</body>
</html>
"""

REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Controle Glicêmico</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style> 
        body { font-family: 'Inter', sans-serif; } 
        .pdf-page {
            page-break-before: always;
            page-break-inside: avoid;
        }
        @media print { 
            html, body { 
                -webkit-print-color-adjust: exact; 
                print-color-adjust: exact; 
                font-size: 8pt;
            } 
            .no-print { display: none !important; }
            #report-content > .pdf-page:first-of-type {
                page-break-before: auto;
            }
            .pdf-day-container {
                display: flex !important;
                flex-direction: row !important;
                gap: 0.5rem !important;
            }
            .pdf-day-glicemias { flex: 0 0 45%; }
            .pdf-day-refeicoes { flex: 0 0 55%; }
            h1, h2, h3, h4, p, li, span, div {
                font-size: inherit !important;
                padding: 0.1rem !important;
                margin: 0 !important;
                line-height: 1.1 !important;
            }
            ul { padding-left: 1rem !important; }
            .shadow-md { box-shadow: none !important; border: 1px solid #eee; }
            .rounded-lg { border-radius: 4px !important; }
        }
    </style>
</head>
<body class="bg-gray-100 text-gray-800">
    <div id="report-content" class="container mx-auto p-4 sm:p-6 md:p-8">
        <header class="mb-8 flex flex-wrap justify-between items-center gap-4 no-print">
            <div>
                <h1 class="text-3xl md:text-4xl font-bold text-blue-700">Relatório de Controle Glicêmico</h1>
                <p class="text-md text-gray-600">Paciente: {{ dados.paciente }} | Período: {{ dados.periodo }}</p>
            </div>
            <div class="flex gap-2">
                <a href="/" class="bg-gray-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-gray-700">Carregar Novo</a>
                <button onclick="saveAsHTML()" class="bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700">Salvar HTML</button>
                <button onclick="exportToPDF()" class="bg-blue-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-blue-700">Exportar para PDF</button>
            </div>
        </header>

        <div class="pdf-page">
            <div id="pdf-header" class="hidden">
                 <h1 class="text-3xl md:text-4xl font-bold text-blue-700">Relatório de Controle Glicêmico</h1>
                <p class="text-md text-gray-600 mb-8">Paciente: {{ dados.paciente }} | Período: {{ dados.periodo }}</p>
            </div>
            <section class="mb-8">
                <h2 class="text-2xl font-semibold mb-4 text-gray-700">Resumo Geral</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
                    <div class="bg-white p-6 rounded-lg shadow-md" title="A média de todas as medições de glicose no período."><h3 class="font-semibold text-gray-500">Glicemia Média</h3><p class="text-4xl font-bold text-blue-600">{{ analise.glicemia_media }} <span class="text-lg">mg/dL</span></p></div>
                    <div class="bg-white p-6 rounded-lg shadow-md" title="Estimativa da Hemoglobina Glicada (A1c) baseada na glicemia média. Fórmula: (Glicemia Média + 46.7) / 28.7."><h3 class="font-semibold text-gray-500">HbA1c Estimada</h3><p class="text-4xl font-bold text-green-600">{{ analise.hba1c_estimada }}<span class="text-lg">%</span></p></div>
                    <div class="bg-white p-6 rounded-lg shadow-md" title="Desvio Padrão (DP). Um valor mais baixo indica maior estabilidade glicêmica."><h3 class="font-semibold text-gray-500">Variabilidade (DP)</h3><p class="text-4xl font-bold text-purple-600">{{ analise.desvio_padrao }}</p></div>
                    <div class="bg-white p-6 rounded-lg shadow-md" title="O valor mais alto e o mais baixo registrados."><h3 class="font-semibold text-gray-500">Medições Extremas</h3><div class="flex items-baseline"><p class="text-2xl font-bold text-red-500">{{ analise.glicemia_max }}</p><span class="mx-2 text-gray-400">/</span><p class="text-2xl font-bold text-sky-500">{{ analise.glicemia_min }}</p><span class="text-sm ml-1">mg/dL</span></div></div>
                    <div class="bg-white p-6 rounded-lg shadow-md" title="O número total de dias com registros no relatório."><h3 class="font-semibold text-gray-500">Total de Dias</h3><p class="text-4xl font-bold text-gray-600">{{ dados.total_dias }}</p></div>
                </div>
            </section>
             <section class="mb-8">
                 <h2 class="text-2xl font-semibold mb-4 text-gray-700">Glicemia Alvo</h2>
                <div class="bg-white p-6 rounded-lg shadow-md">
                    <div class="w-full bg-gray-200 rounded-full h-8 flex overflow-hidden">
                        <div class="bg-sky-500 h-8 flex items-center justify-center text-white font-bold" style="width: {{ analise.tempo_no_alvo.abaixo }}%" title="Abaixo do Alvo">{{ analise.tempo_no_alvo.abaixo }}%</div>
                        <div class="bg-green-500 h-8 flex items-center justify-center text-white font-bold" style="width: {{ analise.tempo_no_alvo.no_alvo }}%" title="No Alvo">{{ analise.tempo_no_alvo.no_alvo }}%</div>
                        <div class="bg-red-500 h-8 flex items-center justify-center text-white font-bold" style="width: {{ analise.tempo_no_alvo.acima }}%" title="Acima do Alvo">{{ analise.tempo_no_alvo.acima }}%</div>
                    </div>
                    <div class="flex justify-between mt-2 text-sm text-gray-600">
                        <span><span class="inline-block w-3 h-3 bg-sky-500 rounded-full mr-1"></span>&lt;70</span>
                        <span><span class="inline-block w-3 h-3 bg-green-500 rounded-full mr-1"></span>70-180</span>
                        <span><span class="inline-block w-3 h-3 bg-red-500 rounded-full mr-1"></span>&gt;180</span>
                    </div>
                </div>
            </section>
        </div>
        
        <div class="pdf-page">
            <h2 class="text-2xl font-semibold mb-4 text-gray-700">Tendência Glicêmica</h2>
            <div class="bg-white p-6 rounded-lg shadow-md h-[600px]">
                <canvas id="glucoseChart"></canvas>
            </div>
        </div>

        <section>
            <h2 class="text-2xl font-semibold my-4 text-gray-700 print:hidden">Registros Detalhados por Dia</h2>
            {% for dia in dados.dias %}
            <div class="pdf-page mb-8">
                <div class="bg-white p-4 rounded-t-lg shadow-md border-b flex flex-wrap justify-between items-center gap-2">
                    <div>
                        <h3 class="text-xl font-bold text-gray-800">{{ dia.data }}</h3>
                        <p class="text-sm text-gray-500">Total: {{ "%.1f"|format(dia.total_kcal) }} kcals / {{ "%.1f"|format(dia.total_carbs) }}g carbs</p>
                    </div>
                    <div class="text-right"><h4 class="font-bold text-lg text-blue-700">Total Insulina do Dia</h4><p class="font-bold text-2xl text-blue-700">{{ "%.0f"|format(dia.total_insulina) }} UI</p></div>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-5 gap-6 p-4 bg-gray-50 rounded-b-lg shadow-md pdf-day-container">
                    <div class="lg:col-span-2 pdf-day-glicemias">
                        <h4 class="font-semibold mb-2 text-lg">Glicemias e Doses</h4>
                        <ul class="space-y-3">
                        {% for glicemia in dia.glicemias %}
                            <li class="p-3 rounded-lg {% if glicemia.valor < 70 %} bg-sky-100 {% elif glicemia.valor > 180 %} bg-red-100 {% else %} bg-green-100 {% endif %}">
                                <div class="flex justify-between items-center"><span class="text-sm text-gray-600">{{ glicemia.hora }} ({{ glicemia.tipo }})</span><span class="font-bold text-gray-800 text-lg">{{ glicemia.valor }} mg/dL</span></div>
                                <div class="mt-2 pt-2 border-t border-gray-300/50"><p class="font-bold text-blue-800">Dose Sugerida: {{ glicemia.dose_sugerida }} UI</p><p class="text-xs text-gray-500 italic">Cálculo: {{ glicemia.calculo }}</p></div>
                            </li>
                        {% endfor %}
                        </ul>
                    </div>
                    <div class="lg:col-span-3 pdf-day-refeicoes">
                         <h4 class="font-semibold mb-2 text-lg">Refeições e Alimentos</h4>
                         {% for refeicao in dia.refeicoes %}
                            <div class="mb-4 bg-white p-3 rounded-md shadow-sm">
                                <p class="font-bold text-md text-gray-700">{{ refeicao.nome }}</p>
                                <p class="text-xs text-gray-500 -mt-1 mb-2">{{ "%.1f"|format(refeicao.total_kcal) }} kcals / {{ "%.1f"|format(refeicao.total_carbs) }}g carbs</p>
                                <ul class="list-disc list-inside text-sm space-y-1 text-gray-600 pl-2">
                                {% for alimento in refeicao.alimentos %}
                                    <li>{{ alimento.nome }} <span class="text-gray-500">({{ alimento.detalhes }})</span></li>
                                {% else %}
                                    <li class="list-none italic">Nenhum alimento detalhado.</li>
                                {% endfor %}
                                </ul>
                            </div>
                         {% else %}
                            <p class="text-gray-500">Nenhuma refeição registrada para este dia.</p>
                         {% endfor %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </section>
    </div>
    <script>
        let glucoseChartInstance;

        // ### ALTERAÇÃO ### - Nova função para salvar a página como um arquivo HTML
        function saveAsHTML() {
            // Usa o nome do arquivo passado pelo Python
            const filename = "{{ filename_html|safe }}";

            // Cria um "Blob" (um objeto tipo arquivo) com o conteúdo HTML da página atual
            const blob = new Blob([document.documentElement.outerHTML], { type: 'text/html;charset=utf-8' });
            
            // Cria um link temporário na memória
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            
            // Simula um clique no link para iniciar o download
            document.body.appendChild(link);
            link.click();
            
            // Limpa o link temporário da memória
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);

            // Informa ao usuário que o download começou
            alert('O download do arquivo "' + filename + '" foi iniciado.');
        }

        function exportToPDF() {
            const element = document.getElementById('report-content');
            const patientName = "{{ dados.paciente }}".replace(/\\s+/g, '_').toLowerCase();
            const period = "{{ dados.periodo }}".replace(/\\s*\\/\\s*/g, '-').replace(/\\s/g, '');
            const filename = `relatorio_glicemico_${patientName}_${period}.pdf`;
            
            const elementForPdf = element.cloneNode(true);
            const pdfHeader = elementForPdf.querySelector('#pdf-header');
            if (pdfHeader) {
                pdfHeader.classList.remove('hidden');
            }

            if (glucoseChartInstance) {
                const imageURL = glucoseChartInstance.toBase64Image('image/jpeg', 1.0);
                const canvasInClone = elementForPdf.querySelector('#glucoseChart');
                if (canvasInClone) {
                    const img = document.createElement('img');
                    img.src = imageURL;
                    img.style.width = '100%';
                    img.style.height = 'auto';
                    canvasInClone.parentNode.replaceChild(img, canvasInClone);
                }
            }

            const opt = { 
                margin: 5, 
                filename: filename, 
                image: { type: 'jpeg', quality: 0.98 }, 
                html2canvas: { scale: 2, useCORS: true, letterRendering: true }, 
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'landscape' },
                pagebreak: { mode: 'css', before: '.pdf-page' }
            };
            html2pdf().from(elementForPdf).set(opt).save();
        }

        const ctx = document.getElementById('glucoseChart');
        if (ctx) {
            const chartData = {{ chart_data|safe }};
            if (window.glucoseChartInstance) {
                window.glucoseChartInstance.destroy();
            }
            window.glucoseChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: chartData.labels,
                    datasets: [{
                        label: 'Glicemia (mg/dL)',
                        data: chartData.data,
                        borderColor: 'rgb(29, 78, 216)',
                        backgroundColor: 'rgba(29, 78, 216, 0.1)',
                        borderWidth: 2,
                        pointRadius: 3,
                        pointBackgroundColor: 'rgb(29, 78, 216)',
                        tension: 0.1,
                        fill: true
                    }]
                },
                options: {
                    animation: false, 
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: false, title: { display: true, text: 'Glicemia (mg/dL)' } }, x: { ticks: { autoSkip: true, maxRotation: 70, minRotation: 45 } } }
                }
            });
        }
    </script>
</body>
</html>
"""
# --- Execução do Servidor ---
if __name__ == '__main__':
    app.run(debug=True)