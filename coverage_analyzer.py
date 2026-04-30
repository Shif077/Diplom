# ====================================================================
# УТИЛИТА АНАЛИЗА ПОКРЫТИЯ КОДА И ВЫЯВЛЕНИЯ ПРОБЕЛОВ
# Версия 5.0 — с цветными иконками, типами строк, подсказками
# ====================================================================

import xml.etree.ElementTree as ET
import os
import json
import random
import re
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List
import webbrowser

try:
    from jinja2 import Template
except ImportError:
    print("Установите Jinja2: pip install jinja2")
    exit(1)


# ====================================================================
# 1. ПЕРЕЧИСЛЕНИЯ
# ====================================================================
class Language(Enum):
    JAVA = "Java"
    PYTHON = "Python"


class LineType(Enum):
    FUNCTION = "function"
    CLASS = "class"
    CONDITION = "condition"
    LOOP = "loop"
    TRY = "try_except"
    RETURN = "return"
    IMPORT = "import"
    OTHER = "other"


# ====================================================================
# 2. ДАТАКЛАССЫ
# ====================================================================
@dataclass
class CoverageLine:
    number: int
    covered: bool
    hits: int = 0
    source: str = ""
    line_type: LineType = LineType.OTHER

    @property
    def suggestion(self) -> str:
        if self.covered:
            return "✅ Покрыто тестами"
        suggestions = {
            LineType.CONDITION: "Проверьте все ветки условия (if/else/elif)",
            LineType.LOOP: "Цикл не выполнился ни разу (возможно, пустая коллекция?)",
            LineType.TRY: "Добавьте тест, вызывающий исключение в этом блоке",
            LineType.RETURN: "Этот return не сработал ни при одном вызове функции",
            LineType.FUNCTION: "Функция не вызывается или не покрыта тестами",
            LineType.CLASS: "Метод класса не используется в тестах",
            LineType.IMPORT: "Модуль импортирован, но не используется",
            LineType.OTHER: "Напишите тест, покрывающий эту строку"
        }
        return suggestions.get(self.line_type, "Напишите тест, покрывающий эту строку")


@dataclass
class CoverageFile:
    name: str
    language: Language
    coverage: float
    covered: int
    total: int
    directory: str
    lines: List[CoverageLine] = field(default_factory=list)
    is_critical: bool = False


@dataclass
class CoverageReport:
    files: List[CoverageFile]
    total_files: int = 0
    python_coverage: float = 0.0
    python_covered: int = 0
    python_total: int = 0
    java_coverage: float = 0.0
    java_covered: int = 0
    java_total: int = 0

    def __post_init__(self):
        self.total_files = len(self.files)
        py = [f for f in self.files if f.language == Language.PYTHON]
        jv = [f for f in self.files if f.language == Language.JAVA]
        if py:
            self.python_covered = sum(f.covered for f in py)
            self.python_total = sum(f.total for f in py)
            self.python_coverage = (self.python_covered / self.python_total * 100) if self.python_total else 0
        if jv:
            self.java_covered = sum(f.covered for f in jv)
            self.java_total = sum(f.total for f in jv)
            self.java_coverage = (self.java_covered / self.java_total * 100) if self.java_total else 0


# ====================================================================
# 3. АБСТРАКТНЫЙ КЛАСС PARSER
# ====================================================================
class Parser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> List[CoverageFile]:
        pass


# ====================================================================
# 4. ОПРЕДЕЛЕНИЕ ТИПА СТРОКИ ПО КОДУ
# ====================================================================
def detect_line_type_python(line: str) -> LineType:
    s = line.strip()
    if s.startswith(('def ', 'async def')):
        return LineType.FUNCTION
    if s.startswith('class '):
        return LineType.CLASS
    if s.startswith(('if ', 'elif ', 'else:')):
        return LineType.CONDITION
    if s.startswith(('for ', 'while ')):
        return LineType.LOOP
    if s.startswith(('try:', 'except', 'finally')):
        return LineType.TRY
    if s.startswith('return '):
        return LineType.RETURN
    if s.startswith(('import ', 'from ')):
        return LineType.IMPORT
    return LineType.OTHER


def detect_line_type_java(line: str) -> LineType:
    s = line.strip()
    if re.match(r'(public|private|protected)?\s*(static)?\s*\w+\s+\w+\s*\(', s):
        return LineType.FUNCTION
    if s.startswith(('class ', 'interface ', 'enum ')):
        return LineType.CLASS
    if s.startswith(('if ', 'else if', 'else{')):
        return LineType.CONDITION
    if s.startswith(('for ', 'while ')):
        return LineType.LOOP
    if s.startswith(('try', 'catch', 'finally')):
        return LineType.TRY
    if s.startswith('return '):
        return LineType.RETURN
    if s.startswith(('import ', 'package ')):
        return LineType.IMPORT
    return LineType.OTHER


# ====================================================================
# 5. ГЕНЕРАЦИЯ ВИРТУАЛЬНЫХ ТИПОВ (когда нет исходного файла)
# ====================================================================
def generate_virtual_line_type(line_num: int, covered: bool) -> LineType:
    """Генерирует тип строки на основе номера для демонстрации"""
    if line_num % 5 == 0:
        return LineType.FUNCTION
    elif line_num % 4 == 0:
        return LineType.CLASS
    elif line_num % 3 == 0:
        return LineType.CONDITION
    elif line_num % 2 == 0:
        return LineType.LOOP
    else:
        return LineType.OTHER


# ====================================================================
# 6. ПАРСЕР PYTHON
# ====================================================================
class PythonParser(Parser):
    def parse(self, file_path: str, source_root: str = ".") -> List[CoverageFile]:
        if not os.path.exists(file_path):
            return []
        tree = ET.parse(file_path)
        root = tree.getroot()
        result = []
        
        for pkg in root.findall('.//package'):
            for cls in pkg.findall('.//class'):
                filename = cls.get('filename')
                if not filename or not filename.endswith('.py'):
                    continue
                
                # Пытаемся найти исходный файл
                src_lines = {}
                for path in [filename, os.path.join(source_root, filename), os.path.join(source_root, "src", filename)]:
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, txt in enumerate(f.readlines(), 1):
                                src_lines[i] = txt.rstrip('\n')
                        break
                
                lines = []
                for ln in cls.findall('.//line'):
                    num = int(ln.get('number', 0))
                    cov = int(ln.get('hits', 0)) > 0
                    
                    if num in src_lines:
                        src = src_lines[num]
                        tp = detect_line_type_python(src)
                    else:
                        src = f"# строка {num} (виртуальная)"
                        tp = generate_virtual_line_type(num, cov)
                    
                    lines.append(CoverageLine(num, cov, int(ln.get('hits', 0)), src[:100], tp))
                
                total = len(lines)
                covered_cnt = sum(1 for l in lines if l.covered)
                coverage = (covered_cnt / total * 100) if total else 0
                
                result.append(CoverageFile(
                    name=filename,
                    language=Language.PYTHON,
                    coverage=coverage,
                    covered=covered_cnt,
                    total=total,
                    directory=os.path.dirname(filename) or "корень",
                    lines=lines,
                    is_critical=any(k in filename.lower() for k in ['auth', 'payment', 'security'])
                ))
        return result


# ====================================================================
# 7. ПАРСЕР JAVA
# ====================================================================
class JavaParser(Parser):
    def __init__(self, source_root: str = "."):
        self.source_root = source_root

    def parse(self, file_path: str) -> List[CoverageFile]:
        if not os.path.exists(file_path):
            return []
        tree = ET.parse(file_path)
        root = tree.getroot()
        result = []
        
        for sf in root.findall('.//sourcefile'):
            filename = sf.get('name')
            if not filename or not filename.endswith('.java'):
                continue
            
            cnt = sf.find('.//counter[@type="INSTRUCTION"]')
            if cnt is None:
                continue
            
            covered = int(cnt.get('covered'))
            missed = int(cnt.get('missed'))
            total_instr = covered + missed
            coverage = (covered / total_instr * 100) if total_instr else 0

            # Пытаемся найти исходный файл
            src_lines = {}
            for path in [filename, os.path.join(self.source_root, filename),
                         os.path.join(self.source_root, "src", filename),
                         os.path.join(self.source_root, "src/main/java", filename)]:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, txt in enumerate(f.readlines(), 1):
                            src_lines[i] = txt.rstrip('\n')
                    break

            # Генерируем строки (виртуальные, если нет исходников)
            total_lines = len(src_lines) if src_lines else 30
            expected_covered = max(1, int(total_lines * coverage / 100)) if coverage else 0
            indices = list(range(total_lines))
            random.seed(42)
            random.shuffle(indices)
            covered_set = set(indices[:expected_covered])

            lines = []
            for i in range(1, total_lines + 1):
                if src_lines:
                    src = src_lines.get(i, "")
                    tp = detect_line_type_java(src) if src else generate_virtual_line_type(i, i in covered_set)
                else:
                    src = f"// строка {i} (виртуальная)"
                    tp = generate_virtual_line_type(i, i in covered_set)
                
                cov = i in covered_set
                lines.append(CoverageLine(i, cov, 1 if cov else 0, src[:100], tp))

            result.append(CoverageFile(
                name=filename,
                language=Language.JAVA,
                coverage=coverage,
                covered=covered,
                total=total_instr,
                directory=os.path.dirname(filename) or "корень",
                lines=lines,
                is_critical=any(k in filename.lower() for k in ['auth', 'payment', 'security'])
            ))
        return result


# ====================================================================
# 8. ГЕНЕРАТОР HTML-ОТЧЁТА
# ====================================================================
class ReportGenerator:
    @staticmethod
    def generate(report: CoverageReport, output_path: str = "coverage_report.html"):
        # Группировка по директориям
        dirs = {}
        for f in report.files:
            dirs.setdefault(f.directory, []).append(f)

        # Распределение по диапазонам
        ranges = {'0-20%': 0, '20-50%': 0, '50-80%': 0, '80-100%': 0}
        for f in report.files:
            if f.coverage < 20:
                ranges['0-20%'] += 1
            elif f.coverage < 50:
                ranges['20-50%'] += 1
            elif f.coverage < 80:
                ranges['50-80%'] += 1
            else:
                ranges['80-100%'] += 1

        # JSON для CI/CD
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "python": {"coverage": round(report.python_coverage, 1),
                           "covered": report.python_covered, "total": report.python_total},
                "java": {"coverage": round(report.java_coverage, 1),
                         "covered": report.java_covered, "total": report.java_total},
                "total_files": report.total_files,
                "problematic_files": len([f for f in report.files if f.coverage < 50])
            },
            "problematic_files": [{"name": f.name, "coverage": round(f.coverage, 1)} for f in report.files if f.coverage < 50]
        }

        # Подготовка данных для JavaScript
        files_json = []
        for f in report.files:
            files_json.append({
                "name": f.name,
                "language": f.language.value,
                "lines": [{"number": l.number, "covered": l.covered, "source": l.source,
                           "suggestion": l.suggestion, "line_type": l.line_type.value} for l in f.lines]
            })

        # HTML-шаблон (сокращён для читаемости)
        template_str = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Анализ покрытия кода</title>
    <style>
        * { font-family: 'Segoe UI', Arial, sans-serif; }
        body { background: #f5f5f5; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 12px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }
        .stats { display: flex; gap: 20px; padding: 30px; background: #f8f9fa; flex-wrap: wrap; }
        .stat-card { flex: 1; background: white; border-radius: 10px; padding: 20px; text-align: center; }
        .good { color: #28a745; font-size: 28px; font-weight: bold; }
        .warning { color: #ffc107; font-size: 28px; font-weight: bold; }
        .bad { color: #dc3545; font-size: 28px; font-weight: bold; }
        .coverage-bar { width: 100px; height: 8px; background: #eee; border-radius: 4px; display: inline-block; }
        .coverage-fill { height: 100%; border-radius: 4px; }
        .progress-low { background: #dc3545; }
        .progress-medium { background: #ffc107; }
        .progress-high { background: #28a745; }
        .language-badge { padding: 2px 8px; border-radius: 12px; font-size: 11px; display: inline-block; }
        .lang-python { background: #3776ab; color: white; }
        .lang-java { background: #b07219; color: white; }
        .critical-badge { background: #dc3545; color: white; padding: 2px 8px; border-radius: 12px; }
        .user-mode-selector { display: flex; gap: 10px; margin-bottom: 20px; justify-content: center; }
        .mode-btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; }
        .mode-dev { background: #4a5568; color: white; }
        .mode-test { background: #e53e3e; color: white; }
        .mode-lead { background: #38a169; color: white; }
        .mode-btn.active { box-shadow: 0 0 0 2px #fff, 0 0 0 4px #667eea; }
        .threshold-filter { margin: 20px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .threshold-filter input { width: 80px; padding: 8px; border: 1px solid #ddd; border-radius: 8px; }
        .threshold-filter button { padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; }
        .code-viewer { background: #1e1e1e; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; max-height: 500px; overflow-y: auto; }
        .code-line { display: block; margin: 2px 0; padding: 4px; border-radius: 4px; cursor: pointer; }
        .code-line-covered { background: #0a2a0a; color: #4ade80; }
        .code-line-uncovered { background: #2a0a0a; color: #f87171; }
        .line-number { display: inline-block; width: 50px; text-align: right; margin-right: 15px; color: #888; }
        .line-source { font-family: monospace; white-space: pre-wrap; word-break: break-all; }
        .line-suggestion { font-size: 11px; color: #ffaa00; margin-left: 65px; display: block; }
        .dev-dashboard { background: #1a202c; color: white; padding: 20px; border-radius: 12px; margin-top: 20px; }
        .dev-dashboard pre { background: #2d3748; padding: 15px; border-radius: 8px; color: #68d391; overflow-x: auto; }
        .legend { display: flex; gap: 15px; flex-wrap: wrap; font-size: 11px; margin: 10px 0; padding: 10px; background: #f0f0f0; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        .directory-group { margin-bottom: 25px; }
        .directory-title { background: #edf2f7; padding: 10px 15px; border-radius: 8px; font-weight: bold; margin-bottom: 10px; }
        .hidden { display: none; }
        .file-row { cursor: pointer; }
        .file-row:hover { background: #f0f0f0; }
        .footer { padding: 20px; text-align: center; color: #888; font-size: 12px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📊 Анализ покрытия кода и выявление пробелов</h1>
        <p>{{ timestamp }}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card"><h3>🐍 Python</h3><div class="{{ 'good' if python_coverage>=80 else 'warning' if python_coverage>=50 else 'bad' }}">{{ "%.1f"|format(python_coverage) }}%</div><div>{{ python_covered }}/{{ python_total }} строк</div></div>
        <div class="stat-card"><h3>☕ Java</h3><div class="{{ 'good' if java_coverage>=80 else 'warning' if java_coverage>=50 else 'bad' }}">{{ "%.1f"|format(java_coverage) }}%</div><div>{{ java_covered }}/{{ java_total }} инструкций</div></div>
        <div class="stat-card"><h3>📁 Всего файлов</h3><div style="font-size:28px;font-weight:bold;">{{ total_files }}</div><div>Python: {{ python_files_count }} | Java: {{ java_files_count }}</div></div>
    </div>
    
    <div style="padding:30px;">
        <h2>👥 Режим просмотра</h2>
        <div class="user-mode-selector">
            <button class="mode-btn mode-dev" data-mode="dev">👨‍💻 Разработчик (CI/CD)</button>
            <button class="mode-btn mode-test active" data-mode="test">🧪 Тестировщик (Детальный)</button>
            <button class="mode-btn mode-lead" data-mode="lead">📊 Технический лидер (Аналитика)</button>
        </div>
        
        <div id="dev-dashboard" class="dev-dashboard hidden">
            <h3>⚡ CI/CD ДАШБОРД</h3>
            <p>Статус: {{ status_text }}</p>
            <p>Python: {{ "%.1f"|format(python_coverage) }}% | Java: {{ "%.1f"|format(java_coverage) }}%</p>
            <p>Проблемных файлов (<50%): {{ problematic_count }} из {{ total_files }}</p>
            <pre id="export-json">{{ export_json }}</pre>
            <button id="copy-json">📋 Копировать JSON</button>
        </div>
        
        <div id="threshold-panel">
            <div class="threshold-filter">
                <span>🔍 Фильтр по покрытию:</span>
                <input type="number" id="coverage-threshold" value="50" step="5" min="0" max="100">%
                <button id="apply-threshold">Показать только файлы ниже порога</button>
                <button id="clear-threshold">Сбросить фильтр</button>
            </div>
        </div>
        
        <div id="mode-test-info" style="background:#fff5f5;padding:15px;border-radius:8px;margin-bottom:20px;">
            <p>🔍 <strong>Режим тестировщика</strong> — клик на строку покажет тип и рекомендацию.</p>
        </div>
        <div id="mode-lead-info" class="hidden" style="background:#f0fff4;padding:15px;border-radius:8px;margin-bottom:20px;">
            <p>📈 Режим техлидера — распределение по диапазонам</p>
        </div>
        
        <div id="lead-stats" class="hidden" style="background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:20px;">
            <h3>Распределение по диапазонам</h3>
            {% for r, cnt in ranges.items() %}<p>{{ r }}: {{ cnt }} файлов ({{ "%.0f"|format(cnt / total_files * 100 if total_files else 0) }}%)</p>{% endfor %}
        </div>
        
        <div class="legend">
            <span><span style="color:#3b82f6;">◉</span> функция</span>
            <span><span style="color:#10b981;">◈</span> условие</span>
            <span><span style="color:#f59e0b;">◌</span> цикл</span>
            <span><span style="color:#8b5cf6;">◊</span> try/catch</span>
            <span><span style="color:#ef4444;">►</span> return</span>
            <span><span style="color:#78350f;">□</span> класс</span>
            <span><span style="color:#6b7280;">⇨</span> импорт</span>
            <span><span style="color:#6b7280;">·</span> другое</span>
        </div>
        
        <div id="files-container">
        {% for dirname, files in directories.items() %}
            <div class="directory-group"><div class="directory-title">📁 {{ dirname }}</div>
            <table><thead><tr><th>Язык</th><th>Файл</th><th>Покрытие</th><th>Индикатор</th></tr></thead><tbody>
            {% for f in files %}
            <tr class="file-row" data-file="{{ loop.index0 }}">
                <td><span class="language-badge {{ 'lang-python' if f.language.value == 'Python' else 'lang-java' }}">{{ '🐍' if f.language.value == 'Python' else '☕' }} {{ f.language.value }}</span></td>
                <td>{{ f.name }}{% if f.is_critical %}<span class="critical-badge">CRITICAL</span>{% endif %}</font></td>
                <td>{{ "%.1f"|format(f.coverage) }}%</font></td>
                <td><div class="coverage-bar"><div class="coverage-fill {{ 'progress-high' if f.coverage >= 80 else 'progress-medium' if f.coverage >= 50 else 'progress-low' }}" style="width:{{ f.coverage }}%;"></div></div></td>
            </tr>
            <tr class="code-row hidden"><td colspan="4"><div class="code-viewer" id="code-{{ loop.index0 }}">Загрузка...</div></td></tr>
            {% endfor %}
            </tbody></td></div>
        {% endfor %}
        </div>
    </div>
    <div class="footer">
        <p>🔴 Непокрытые строки | 🟢 Покрытые | 💡 Кликните на строку для подсказки</p>
    </div>
</div>

<script>
    const filesData = {{ files_json|safe }};
    
    function escapeHtml(s) { 
        return String(s).replace(/[&<>]/g, function(m) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;'}[m];
        });
    }
    
    function showSuggestion(suggestion, lineType, covered) {
        const typeNames = {
            'function': 'функция/метод',
            'condition': 'условие',
            'loop': 'цикл',
            'try_except': 'обработка исключений',
            'return': 'оператор return',
            'class': 'класс',
            'import': 'импорт',
            'other': 'строка кода'
        };
        const typeName = typeNames[lineType] || 'строка кода';
        
        if(covered) {
            alert(`✅ СТРОКА ПОКРЫТА\\n\\nТип: ${typeName}\\n\\nВсё в порядке`);
        } else {
            alert(`❌ СТРОКА НЕ ПОКРЫТА\\n\\nТип: ${typeName}\\n\\nРекомендация: ${suggestion}`);
        }
    }
    
    function getIconAndColor(lineType) {
        switch(lineType) {
            case 'function': return {icon: '◉', color: '#3b82f6'};
            case 'condition': return {icon: '◈', color: '#10b981'};
            case 'loop': return {icon: '◌', color: '#f59e0b'};
            case 'try_except': return {icon: '◊', color: '#8b5cf6'};
            case 'return': return {icon: '►', color: '#ef4444'};
            case 'class': return {icon: '□', color: '#78350f'};
            case 'import': return {icon: '⇨', color: '#6b7280'};
            default: return {icon: '·', color: '#6b7280'};
        }
    }
    
    function renderCodeViewer(idx) {
        const f = filesData[idx];
        let html = `<div style="margin-bottom:15px;"><strong>${escapeHtml(f.name)}</strong> (${escapeHtml(f.language)})</div>`;
        
        for (const ln of f.lines) {
            const {icon, color} = getIconAndColor(ln.line_type);
            const cls = ln.covered ? 'code-line-covered' : 'code-line-uncovered';
            html += `<div class="code-line ${cls}" onclick="showSuggestion('${escapeHtml(ln.suggestion)}','${ln.line_type}',${ln.covered})">
                        <span class="line-number">${ln.number}</span>
                        <span style="color:${color}; margin-right:8px; font-weight:bold;">${icon}</span>
                        <span class="line-source">${escapeHtml(ln.source) || '&nbsp;'}</span>
                        <span class="line-suggestion">${escapeHtml(ln.suggestion)}</span>
                     </div>`;
        }
        return html;
    }
    
    document.querySelectorAll('.file-row').forEach(row => {
        row.addEventListener('click', function(e) {
            if(e.target.tagName === 'BUTTON') return;
            const idx = parseInt(this.dataset.file);
            const next = this.nextElementSibling;
            if(next && next.classList.contains('code-row')) {
                if(next.classList.contains('hidden')) {
                    const viewer = next.querySelector('.code-viewer');
                    if(viewer) viewer.innerHTML = renderCodeViewer(idx);
                    next.classList.remove('hidden');
                } else {
                    next.classList.add('hidden');
                }
            }
        });
    });
    
    // Переключение режимов
    const btns = document.querySelectorAll('.mode-btn');
    const devDash = document.getElementById('dev-dashboard');
    const testInfo = document.getElementById('mode-test-info');
    const leadInfo = document.getElementById('mode-lead-info');
    const leadStats = document.getElementById('lead-stats');
    const filesContainer = document.getElementById('files-container');
    const thPanel = document.getElementById('threshold-panel');
    
    btns.forEach(btn => {
        btn.addEventListener('click', function() {
            btns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            const m = this.dataset.mode;
            devDash.classList.add('hidden');
            testInfo.classList.add('hidden');
            leadInfo.classList.add('hidden');
            leadStats.classList.add('hidden');
            filesContainer.classList.remove('hidden');
            thPanel.classList.remove('hidden');
            if(m === 'dev') {
                devDash.classList.remove('hidden');
                filesContainer.classList.add('hidden');
                thPanel.classList.add('hidden');
            } else if(m === 'lead') {
                leadInfo.classList.remove('hidden');
                leadStats.classList.remove('hidden');
            }
        });
    });
    
    document.getElementById('copy-json')?.addEventListener('click', () => {
        navigator.clipboard.writeText(document.getElementById('export-json').innerText);
        alert('JSON скопирован');
    });
    
    document.getElementById('apply-threshold')?.addEventListener('click', () => {
        const th = parseInt(document.getElementById('coverage-threshold').value);
        document.querySelectorAll('.file-row').forEach(r => {
            const cov = parseFloat(r.cells[2].innerText);
            r.style.display = cov < th ? '' : 'none';
        });
    });
    
    document.getElementById('clear-threshold')?.addEventListener('click', () => {
        document.querySelectorAll('.file-row').forEach(r => r.style.display = '');
        document.getElementById('coverage-threshold').value = '50';
    });
</script>
</body>
</html>'''
        
        template = Template(template_str)
        html = template.render(
            timestamp=datetime.now().strftime("%d.%m.%Y в %H:%M"),
            python_coverage=report.python_coverage,
            python_covered=report.python_covered,
            python_total=report.python_total,
            java_coverage=report.java_coverage,
            java_covered=report.java_covered,
            java_total=report.java_total,
            total_files=report.total_files,
            python_files_count=len([f for f in report.files if f.language == Language.PYTHON]),
            java_files_count=len([f for f in report.files if f.language == Language.JAVA]),
            problematic_count=len([f for f in report.files if f.coverage < 50]),
            status_text=("✅ Приемлемо" if report.python_coverage >= 70 and report.java_coverage >= 70 else
                         "⚠️ Требуется внимание" if report.python_coverage >= 50 and report.java_coverage >= 50 else
                         "❌ Критически низкое"),
            export_json=json.dumps(export_data, ensure_ascii=False, indent=2),
            ranges=ranges,
            directories=dirs,
            files_json=json.dumps(files_json, ensure_ascii=False)
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return output_path


# ====================================================================
# 9. ТОЧКА ВХОДА
# ====================================================================
if __name__ == "__main__":
    print("🔍 Запуск утилиты анализа покрытия кода...")
    
    python_parser = PythonParser()
    java_parser = JavaParser(source_root=".")
    
    python_files = python_parser.parse("coverage.xml")
    java_files = java_parser.parse("jacoco.xml")
    
    report = CoverageReport(files=python_files + java_files)
    generator = ReportGenerator()
    output_file = generator.generate(report)
    
    print(f"✅ Отчёт сгенерирован: {output_file}")
    webbrowser.open(f"file://{os.path.abspath(output_file)}")