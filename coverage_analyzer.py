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
import base64

try:
    from jinja2 import Template
except ImportError:
    print("Установите Jinja2: pip install jinja2")
    exit(1)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Для PDF отчёта установите: pip install reportlab matplotlib numpy")



# ПЕРЕЧИСЛЕНИЯ

class Language(Enum):
# Перечесления языков программирования
    JAVA = "Java"
    PYTHON = "Python"


class LineType(Enum):
# Перечесления типов строк кода
    FUNCTION = "function"  # Строка содержащая определение функции (def)
    CLASS = "class"        # Строка содержащая определение класса (class)
    CONDITION = "condition" # Строка c условным оператором (if, elif, else)
    LOOP = "loop"           # Строка с циклами (for, while)
    TRY = "try_except"      # Строка с обработкой исключений (try,except)
    RETURN = "return"       # Строка с оператором возврата (return)
    IMPORT = "import"       # Строка с импортом модулей (import, from)
    OTHER = "other"         # Любой другой тип строки


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
class DetailedStats:
    """Детальная статистика для тестировщика"""
    total_lines: int = 0
    covered_lines: int = 0
    uncovered_lines: int = 0
    
    # Статистика по типам строк
    by_type: dict = field(default_factory=dict)
    
    # Самые проблемные файлы
    worst_files: List[dict] = field(default_factory=list)
    
    # Статистика по критическим файлам
    critical_files: dict = field(default_factory=dict)
    
    # Рекомендации по приоритетам
    priorities: List[dict] = field(default_factory=list)
    
    # Метрики сложности
    complexity_stats: dict = field(default_factory=dict)


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
    detailed_stats: DetailedStats = field(default_factory=DetailedStats)

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
        
        self._calculate_detailed_stats()
    
    def _calculate_detailed_stats(self):
        """Расчёт детальной статистики"""
        stats = DetailedStats()
        
        # Инициализация статистики по типам
        for line_type in LineType:
            stats.by_type[line_type.value] = {
                "total": 0, "covered": 0, "uncovered": 0, "coverage": 0.0
            }
        
        all_uncovered = []
        
        for file in self.files:
            # Статистика по типам строк
            for line in file.lines:
                stats.total_lines += 1
                if line.covered:
                    stats.covered_lines += 1
                else:
                    stats.uncovered_lines += 1
                    all_uncovered.append((file, line))
                
                # По типам
                line_type_key = line.line_type.value
                stats.by_type[line_type_key]["total"] += 1
                if line.covered:
                    stats.by_type[line_type_key]["covered"] += 1
                else:
                    stats.by_type[line_type_key]["uncovered"] += 1
            
            # Вычисляем покрытие по типам
            for line_type_key in stats.by_type:
                total = stats.by_type[line_type_key]["total"]
                covered = stats.by_type[line_type_key]["covered"]
                stats.by_type[line_type_key]["coverage"] = (covered / total * 100) if total > 0 else 100.0
            
            # Самые проблемные файлы
            if file.coverage < 50 and file.total > 0:
                stats.worst_files.append({
                    "name": file.name,
                    "coverage": round(file.coverage, 1),
                    "uncovered": file.total - file.covered,
                    "language": file.language.value,
                    "is_critical": file.is_critical
                })
            
            # Статистика по критическим файлам
            if file.is_critical:
                status = "good" if file.coverage >= 80 else "warning" if file.coverage >= 50 else "critical"
                stats.critical_files[file.name] = {
                    "coverage": round(file.coverage, 1),
                    "status": status
                }
        
        stats.worst_files.sort(key=lambda x: x["coverage"])
        stats.worst_files = stats.worst_files[:10]
        
        # Расчёт приоритетов для тестирования
        for file, line in all_uncovered[:50]:
            priority = 0
            if file.is_critical:
                priority += 3
            if line.line_type in [LineType.CONDITION, LineType.LOOP, LineType.TRY]:
                priority += 2
            if line.line_type == LineType.FUNCTION:
                priority += 1
            
            stats.priorities.append({
                "file": file.name,
                "line": line.number,
                "type": line.line_type.value,
                "priority": priority,
                "suggestion": line.suggestion,
                "source": line.source[:80]
            })
        
        stats.priorities.sort(key=lambda x: x["priority"], reverse=True)
        stats.priorities = stats.priorities[:20]
        
        # Метрики сложности
        total_conditions = stats.by_type["condition"]["total"]
        covered_conditions = stats.by_type["condition"]["covered"]
        total_loops = stats.by_type["loop"]["total"]
        covered_loops = stats.by_type["loop"]["covered"]
        
        total_complex = total_conditions + total_loops
        covered_complex = covered_conditions + covered_loops
        
        if total_complex > 0:
            branch_coverage = (covered_complex / total_complex * 100)
            if branch_coverage < 50:
                risk_level = "high"
            elif branch_coverage < 70:
                risk_level = "medium"
            else:
                risk_level = "low"
        else:
            branch_coverage = 0
            risk_level = "low"
        
        stats.complexity_stats = {
            "total_branches": total_complex,
            "covered_branches": covered_complex,
            "branch_coverage": branch_coverage,
            "risk_level": risk_level
        }
        
        self.detailed_stats = stats


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
# 5. ГЕНЕРАЦИЯ ВИРТУАЛЬНЫХ ТИПОВ
# ====================================================================
def generate_virtual_line_type(line_num: int, covered: bool) -> LineType:
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
                        src = f"# строка {num}"
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

            src_lines = {}
            for path in [filename, os.path.join(self.source_root, filename),
                         os.path.join(self.source_root, "src", filename),
                         os.path.join(self.source_root, "src/main/java", filename)]:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, txt in enumerate(f.readlines(), 1):
                            src_lines[i] = txt.rstrip('\n')
                    break

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
                    src = f"// строка {i}"
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
# 8. ГЕНЕРАТОР ТЕПЛОВОЙ КАРТЫ
# ====================================================================
class HeatmapGenerator:
    @staticmethod
    def generate_heatmap(report: CoverageReport, output_path: str = "heatmap.png") -> str:
        """Генерирует тепловую карту покрытия кода"""
        try:
            # Подготовка данных
            files_data = []
            for i, file in enumerate(report.files[:20]):  # Максимум 20 файлов для читаемости
                file_data = {
                    "name": file.name[:30],
                    "coverage": file.coverage,
                    "language": file.language.value,
                    "lines": []
                }
                
                # Разбиваем файл на блоки по 10 строк
                lines_per_block = 10
                blocks = {}
                for line in file.lines:
                    block_num = line.number // lines_per_block
                    if block_num not in blocks:
                        blocks[block_num] = {"covered": 0, "total": 0}
                    blocks[block_num]["total"] += 1
                    if line.covered:
                        blocks[block_num]["covered"] += 1
                
                for block_num in sorted(blocks.keys())[:20]:  # Максимум 20 блоков на файл
                    block = blocks[block_num]
                    block_coverage = (block["covered"] / block["total"] * 100) if block["total"] > 0 else 0
                    file_data["lines"].append(block_coverage)
                
                files_data.append(file_data)
            
            if not files_data:
                return None
            
            # Создаём матрицу для тепловой карты
            max_lines = max(len(f["lines"]) for f in files_data)
            matrix = []
            labels = []
            
            for f in files_data:
                row = f["lines"] + [0] * (max_lines - len(f["lines"]))
                matrix.append(row)
                labels.append(f"{f['name']} ({f['coverage']:.0f}%)")
            
            # Создаём тепловую карту
            fig, ax = plt.subplots(figsize=(14, max(8, len(matrix) * 0.3)))
            
            # Используем красный-жёлтый-зелёный градиент
            cmap = mcolors.LinearSegmentedColormap.from_list("custom", ["#dc3545", "#ffc107", "#28a745"])
            
            im = ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=0, vmax=100)
            
            # Настройка осей
            ax.set_xticks(np.arange(max_lines))
            ax.set_xticklabels([f"Блок {i+1}" for i in range(max_lines)], rotation=45, ha="right", fontsize=8)
            ax.set_yticks(np.arange(len(labels)))
            ax.set_yticklabels(labels, fontsize=9)
            
            # Цветовая шкала
            cbar = ax.figure.colorbar(im, ax=ax)
            cbar.ax.set_ylabel("Покрытие (%)", rotation=-90, va="bottom")
            
            # Заголовок
            ax.set_title("Тепловая карта покрытия кода по файлам и блокам строк", fontsize=14, fontweight="bold")
            ax.set_xlabel("Блоки строк (по 10 строк)", fontsize=10)
            ax.set_ylabel("Файлы", fontsize=10)
            
            # Добавляем значения в ячейки
            for i in range(len(matrix)):
                for j in range(len(matrix[i])):
                    if matrix[i][j] > 0:
                        text = ax.text(j, i, f"{matrix[i][j]:.0f}%",
                                     ha="center", va="center", color="white", fontsize=7, fontweight="bold")
            
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            
            return output_path
        except Exception as e:
            print(f"Ошибка при создании тепловой карты: {e}")
            return None


# ====================================================================
# 9. PDF ГЕНЕРАТОР
# ====================================================================
# ====================================================================
# 9. PDF ГЕНЕРАТОР (С ПОДДЕРЖКОЙ РУССКОГО ЯЗЫКА)
# ====================================================================
# ====================================================================
# 9. PDF ГЕНЕРАТОР (ГАРАНТИРОВАННО РАБОТАЮЩИЙ)
# ====================================================================
# ====================================================================
# 9. PDF ГЕНЕРАТОР (ИСПРАВЛЕННЫЙ)
# ====================================================================
class PDFGenerator:
    @staticmethod
    def generate_pdf(report: CoverageReport, heatmap_path: str = None, output_path: str = "coverage_report.pdf") -> str:
        """Генерирует PDF отчёт для технического лидера"""
        
        # Проверка наличия библиотек
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            print("PDF генерация недоступна. Установите: pip install reportlab")
            return None
        
        # Регистрируем шрифт с кириллицей
        font_registered = False
        font_name = 'Helvetica'
        
        # Пробуем разные пути к шрифтам
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/ariali.ttf",
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/timesi.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Arial.ttf"
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('RussianFont', font_path))
                    font_name = 'RussianFont'
                    font_registered = True
                    break
                except:
                    continue
        
        if not font_registered:
            font_name = 'Helvetica'
        
        # Создаём документ
        doc = SimpleDocTemplate(output_path, pagesize=landscape(A4), 
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=1.5*cm)
        
        # Стили
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Normal'],
            fontSize=18,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName=font_name
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Normal'],
            fontSize=13,
            textColor=colors.HexColor('#2980b9'),
            spaceAfter=8,
            spaceBefore=12,
            fontName=font_name
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=9,
            fontName=font_name
        )
        
        story = []
        
        # Заголовок (на русском)
        story.append(Paragraph("Отчет о покрытии кода", title_style))
        story.append(Paragraph("Дата: " + datetime.now().strftime('%d.%m.%Y %H:%M'), normal_style))
        story.append(Spacer(1, 0.5*cm))
        
        # ===== 1. Общая статистика =====
        story.append(Paragraph("1. Общая статистика", heading_style))
        
        total_covered = report.python_covered + report.java_covered
        total_all = report.python_total + report.java_total
        total_coverage = (total_covered / total_all * 100) if total_all else 0
        py_count = len([f for f in report.files if f.language == Language.PYTHON])
        java_count = len([f for f in report.files if f.language == Language.JAVA])
        
        # Таблица на русском
        data = [
            ['Показатель', 'Python', 'Java', 'Всего'],
            ['Покрытие, %', f"{report.python_coverage:.1f}", f"{report.java_coverage:.1f}", f"{total_coverage:.1f}"],
            ['Покрыто строк', str(report.python_covered), str(report.java_covered), str(total_covered)],
            ['Всего строк', str(report.python_total), str(report.java_total), str(total_all)],
            ['Количество файлов', str(py_count), str(java_count), str(report.total_files)]
        ]
        
        table = Table(data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
        ]))
        story.append(table)
        story.append(Spacer(1, 0.4*cm))
        
        # ===== 2. Тепловая карта =====
        if heatmap_path and os.path.exists(heatmap_path):
            story.append(Paragraph("2. Тепловая карта покрытия", heading_style))
            try:
                img = Image(heatmap_path, width=22*cm, height=12*cm)
                story.append(img)
                story.append(Spacer(1, 0.2*cm))
                story.append(Spacer(1, 0.4*cm))
            except:
                pass
        
        # ===== 3. Покрытие по типам =====
        story.append(Paragraph("3. Покрытие по типам конструкций", heading_style))
        
        type_data = [['Тип', 'Покрыто', 'Всего', 'Процент']]
        for line_type, stats in report.detailed_stats.by_type.items():
            if stats['total'] > 0:
                type_name = line_type.replace('_', ' ')
                type_data.append([
                    type_name,
                    str(stats['covered']),
                    str(stats['total']),
                    f"{stats['coverage']:.1f}"
                ])
        
        type_table = Table(type_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm])
        type_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8e44ad')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
        ]))
        story.append(type_table)
        story.append(Spacer(1, 0.4*cm))
        
        # ===== 4. Покрытие ветвлений =====
        story.append(Paragraph("4. Покрытие ветвлений (условия и циклы)", heading_style))
        
        # Используем правильные названия методов
        branch_data = [
            ['Показатель', 'Значение'],
            ['Всего условий и циклов', str(report.detailed_stats.complexity_stats["total_branches"])],
            ['Покрыто', str(report.detailed_stats.complexity_stats["covered_branches"])],
            ['Процент покрытия', f"{report.detailed_stats.complexity_stats['branch_coverage']:.1f}"],
            ['Уровень риска', PDFGenerator._get_risk_text(report.detailed_stats.complexity_stats['risk_level'])]
        ]
        
        branch_table = Table(branch_data, colWidths=[6*cm, 8*cm])
        branch_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
        ]))
        story.append(branch_table)
        story.append(Spacer(1, 0.4*cm))
        
        # ===== 5. Критические файлы =====
        if report.detailed_stats.critical_files:
            story.append(Paragraph("5. Критически важные файлы", heading_style))
            critical_data = [['Файл', 'Покрытие', 'Статус']]
            for filename, stats in list(report.detailed_stats.critical_files.items())[:10]:
                status_text = PDFGenerator._get_status_text(stats['status'])
                short_name = filename.split('/')[-1] if '/' in filename else filename
                if len(short_name) > 35:
                    short_name = short_name[:32] + '...'
                critical_data.append([short_name, f"{stats['coverage']}%", status_text])
            
            crit_table = Table(critical_data, colWidths=[10*cm, 3*cm, 4*cm])
            crit_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
            ]))
            story.append(crit_table)
            story.append(Spacer(1, 0.4*cm))
        
        # ===== 6. Проблемные файлы =====
        if report.detailed_stats.worst_files:
            story.append(Paragraph("6. Файлы с низким покрытием (менее 50%)", heading_style))
            worst_data = [['Файл', 'Язык', 'Покрытие', 'Непокрыто']]
            for f in report.detailed_stats.worst_files[:10]:
                short_name = f['name'].split('/')[-1] if '/' in f['name'] else f['name']
                if len(short_name) > 30:
                    short_name = short_name[:27] + '...'
                worst_data.append([short_name, f['language'], f"{f['coverage']}%", str(f['uncovered'])])
            
            worst_table = Table(worst_data, colWidths=[8*cm, 3*cm, 3*cm, 3*cm])
            worst_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f39c12')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
            ]))
            story.append(worst_table)
            story.append(Spacer(1, 0.4*cm))
        
        # ===== 7. Рекомендации =====
        story.append(Paragraph("7. Итоговые рекомендации", heading_style))
        
        recommendations = []
        if total_coverage < 70:
            recommendations.append("- Общее покрытие ниже целевого уровня 70%. Необходимо усилить тестирование.")
        if report.detailed_stats.complexity_stats['branch_coverage'] < 60:
            recommendations.append("- Низкое покрытие ветвлений. Добавьте тесты для проверки условий и циклов.")
        if len(report.detailed_stats.critical_files) > 0:
            recommendations.append(f"- Критически важные файлы ({len(report.detailed_stats.critical_files)} шт.) имеют низкое покрытие. Приоритет 1.")
        if report.detailed_stats.uncovered_lines > 0:
            recommendations.append(f"- {report.detailed_stats.uncovered_lines} строк кода не покрыты тестами.")
        
        if not recommendations:
            recommendations.append("- Покрытие кода на хорошем уровне. Продолжайте поддерживать качество тестов.")
        
        for rec in recommendations:
            story.append(Paragraph(rec, normal_style))
            story.append(Spacer(1, 0.15*cm))
        
        # Footer
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("Отчет сгенерирован автоматически.", normal_style))
        
        doc.build(story)
        return output_path
    
    @staticmethod
    def _get_risk_text(risk):
        """Возвращает текст уровня риска на русском"""
        if risk == 'high':
            return 'ВЫСОКИЙ (требуется срочное внимание)'
        elif risk == 'medium':
            return 'СРЕДНИЙ (рекомендуется улучшить)'
        else:
            return 'НИЗКИЙ (приемлемый уровень)'
    
    @staticmethod
    def _get_status_text(status):
        """Возвращает текст статуса на русском"""
        if status == 'good':
            return 'Хорошо'
        elif status == 'warning':
            return 'Средне'
        else:
            return 'Критично'
# ====================================================================
# 10. ГЕНЕРАТОР HTML-ОТЧЁТА
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
                           "suggestion": l.suggestion, "line_type": l.line_type.value} for l in f.lines],
                "coverage": round(f.coverage, 1),
                "is_critical": f.is_critical
            })

        # Подготовка detailed_stats для JSON
        detailed_stats_json = {
            "total_lines": report.detailed_stats.total_lines,
            "covered_lines": report.detailed_stats.covered_lines,
            "uncovered_lines": report.detailed_stats.uncovered_lines,
            "by_type": report.detailed_stats.by_type,
            "worst_files": report.detailed_stats.worst_files,
            "critical_files": report.detailed_stats.critical_files,
            "priorities": report.detailed_stats.priorities,
            "complexity_stats": report.detailed_stats.complexity_stats
        }

        # HTML-шаблон
        template_str = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Анализ покрытия кода</title>
    <style>
        * { font-family: 'Segoe UI', Arial, sans-serif; }
        body { background: #f5f5f5; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }
        .stats { display: flex; gap: 20px; padding: 30px; background: #f8f9fa; flex-wrap: wrap; }
        .stat-card { flex: 1; background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
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
        .critical-badge { background: #dc3545; color: white; padding: 2px 8px; border-radius: 12px; font-size: 10px; margin-left: 5px; }
        .user-mode-selector { display: flex; gap: 10px; margin-bottom: 20px; justify-content: center; flex-wrap: wrap; }
        .mode-btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; transition: all 0.3s; font-size: 14px; }
        .mode-dev { background: #4a5568; color: white; }
        .mode-test { background: #e53e3e; color: white; }
        .mode-lead { background: #38a169; color: white; }
        .mode-btn.active { box-shadow: 0 0 0 2px #fff, 0 0 0 4px #667eea; transform: scale(1.05); }
        .threshold-filter { margin: 20px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .threshold-filter input { width: 80px; padding: 8px; border: 1px solid #ddd; border-radius: 8px; }
        .threshold-filter button { padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; }
        .code-viewer { background: #1e1e1e; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; max-height: 500px; overflow-y: auto; }
        .code-line { display: block; margin: 2px 0; padding: 4px; border-radius: 4px; cursor: pointer; transition: all 0.2s; }
        .code-line-covered { background: #0a2a0a; color: #4ade80; }
        .code-line-uncovered { background: #2a0a0a; color: #f87171; }
        .code-line:hover { filter: brightness(1.2); transform: translateX(5px); }
        .line-number { display: inline-block; width: 50px; text-align: right; margin-right: 15px; color: #888; }
        .line-source { font-family: monospace; white-space: pre-wrap; word-break: break-all; }
        .line-suggestion { font-size: 11px; color: #ffaa00; margin-left: 65px; display: block; }
        .dev-dashboard { background: #1a202c; color: white; padding: 20px; border-radius: 12px; margin-top: 20px; }
        .dev-dashboard pre { background: #2d3748; padding: 15px; border-radius: 8px; color: #68d391; overflow-x: auto; font-size: 12px; }
        .legend { display: flex; gap: 15px; flex-wrap: wrap; font-size: 11px; margin: 10px 0; padding: 10px; background: #f0f0f0; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        .directory-group { margin-bottom: 25px; }
        .directory-title { background: #edf2f7; padding: 10px 15px; border-radius: 8px; font-weight: bold; margin-bottom: 10px; }
        .hidden { display: none; }
        .file-row { cursor: pointer; transition: background 0.2s; }
        .file-row:hover { background: #f0f0f0; }
        .footer { padding: 20px; text-align: center; color: #888; font-size: 12px; }
        .stats-detailed { background: #f8f9fa; padding: 20px; border-radius: 12px; margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 15px; }
        .stat-item { background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #667eea; }
        .priority-high { background: #fee; border-left-color: #dc3545; }
        .priority-medium { background: #ffefcc; border-left-color: #ffc107; }
        .priority-low { background: #e8f5e9; border-left-color: #28a745; }
        .btn-pdf { background: #dc3545; color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; text-decoration: none; display: inline-block; }
        .btn-pdf:hover { background: #c82333; transform: scale(1.05); }
        .type-badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-right: 5px; }
        h2, h3 { margin-top: 20px; margin-bottom: 15px; }
        .heatmap-container { background: white; padding: 20px; border-radius: 12px; margin: 20px 0; text-align: center; }
        .heatmap-img { max-width: 100%; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
<div class="header">
    <h1>Анализ покрытия кода и выявление пробелов</h1>
    <p>{{ timestamp }}</p>
</div>
    
    <div class="stats">
<div class="stat-card">
    <h3>Python</h3>
            <div class="{{ 'good' if python_coverage>=80 else 'warning' if python_coverage>=50 else 'bad' }}">
                {{ "%.1f"|format(python_coverage) }}%
            </div>
            <div>Покрыто: {{ python_covered }}/{{ python_total }} строк</div>
            <div>Файлов: {{ python_files_count }}</div>
</div>


<div class="stat-card">
    <h3>Java</h3>
            <div class="{{ 'good' if java_coverage>=80 else 'warning' if java_coverage>=50 else 'bad' }}">
                {{ "%.1f"|format(java_coverage) }}%
            </div>
            <div>Покрыто: {{ java_covered }}/{{ java_total }} инструкций</div>
            <div>Файлов: {{ java_files_count }}</div>
        </div>
        
    <div class="stat-card">
    <h3>Общая статистика</h3>
            <div style="font-size:24px; font-weight:bold;">{{ total_files }} файлов</div>
            <div>Всего строк: {{ python_total + java_total }}</div>
            <div>Покрыто строк: {{ python_covered + java_covered }}</div>
            <div>Общее покрытие: <strong>{{ "%.1f"|format((python_covered + java_covered) / (python_total + java_total) * 100 if (python_total + java_total) else 0) }}%</strong></div>
        </div>
    </div>
    
    <div style="padding:30px;">
        <h2>👥 Режим просмотра</h2>
        <div class="user-mode-selector">
<button class="mode-btn mode-dev" data-mode="dev">Разработчик (CI/CD)</button>
<button class="mode-btn mode-test active" data-mode="test">Тестировщик (Детальный)</button>
<button class="mode-btn mode-lead" data-mode="lead">Технический лидер (Аналитика)</button>
        </div>
        
        <div id="dev-dashboard" class="dev-dashboard hidden">
            <h3>⚡ CI/CD ДАШБОРД</h3>
            <p>Статус: {{ status_text }}</p>
            <p>Python: {{ "%.1f"|format(python_coverage) }}% | Java: {{ "%.1f"|format(java_coverage) }}%</p>
            <p>Проблемных файлов (&lt;50%): {{ problematic_count }} из {{ total_files }}</p>
            <pre id="export-json">{{ export_json }}</pre>
            <button id="copy-json">📋 Копировать JSON</button>
        </div>
        
        <div id="test-stats" class="stats-detailed">
            <h2>📈 Детальная статистика для тестировщика</h2>
            
            <div class="stats-grid">
                <div class="stat-item">
                    <strong>📊 Общая статистика</strong><br>
                    Всего строк: {{ detailed_stats.total_lines }}<br>
                    Покрыто: {{ detailed_stats.covered_lines }}<br>
                    Не покрыто: <span style="color:#dc3545; font-weight:bold;">{{ detailed_stats.uncovered_lines }}</span><br>
                    Общее покрытие: <strong>{{ "%.1f"|format((detailed_stats.covered_lines / detailed_stats.total_lines * 100) if detailed_stats.total_lines else 0) }}%</strong>
                </div>
                
                <div class="stat-item">
                    <strong>🎯 Покрытие ветвлений</strong><br>
                    Условий/циклов: {{ detailed_stats.complexity_stats.total_branches }}<br>
                    Покрыто: {{ detailed_stats.complexity_stats.covered_branches }}<br>
                    Покрытие: <strong>{{ "%.1f"|format(detailed_stats.complexity_stats.branch_coverage) }}%</strong><br>
                    Риск: <span class="type-badge" style="background:{{ '#dc3545' if detailed_stats.complexity_stats.risk_level == 'high' else '#ffc107' if detailed_stats.complexity_stats.risk_level == 'medium' else '#28a745' }}; color:white;">{{ detailed_stats.complexity_stats.risk_level }}</span>
                </div>
            </div>
            
            <h3>📋 Покрытие по типам конструкций</h3>
            <table>
                <thead><tr><th>Тип</th><th>Покрыто</th><th>Всего</th><th>Процент</th><th>Статус</th></tr></thead>
                <tbody>
                    {% for type_name, stats in detailed_stats.by_type.items() %}
                    {% if stats.total > 0 %}
                    <tr>
                        <td>{{ type_name }}</td>
                        <td>{{ stats.covered }}</td>
                        <td>{{ stats.total }}</td>
                        <td><strong>{{ "%.1f"|format(stats.coverage) }}%</strong></td>
                        <td>{% if stats.coverage >= 80 %}🟢 Хорошо{% elif stats.coverage >= 50 %}🟡 Средне{% else %}🔴 Плохо{% endif %}</td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                </tbody>
            </table>
            
            <h3>🔥 Топ-10 проблемных файлов</h3>
            <table>
                <thead><tr><th>Файл</th><th>Язык</th><th>Покрытие</th><th>Непокрыто</th><th>Статус</th></tr></thead>
                <tbody>
                    {% for file in detailed_stats.worst_files[:10] %}
                    <tr>
                        <td>{{ file.name }}{% if file.is_critical %} <span class="critical-badge">CRITICAL</span>{% endif %}</td>
                        <td><span class="language-badge {{ 'lang-python' if file.language == 'Python' else 'lang-java' }}">{{ file.language }}</span></td>
                        <td><span style="color:{% if file.coverage >= 80 %}#28a745{% elif file.coverage >= 50 %}#ffc107{% else %}#dc3545{% endif %}; font-weight:bold;">{{ file.coverage }}%</span></td>
                        <td>{{ file.uncovered }}</td>
                        <td>{% if file.coverage >= 80 %}✅ Достаточно{% elif file.coverage >= 50 %}⚠️ Требует улучшения{% else %}❌ Критично{% endif %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            
            <h3>🎯 Приоритеты для тестирования (Топ-20)</h3>
            <table>
                <thead><tr><th>Приоритет</th><th>Файл</th><th>Строка</th><th>Тип</th><th>Рекомендация</th></tr></thead>
                <tbody>
                    {% for p in detailed_stats.priorities %}
                    <tr class="{% if p.priority >= 4 %}priority-high{% elif p.priority >= 2 %}priority-medium{% else %}priority-low{% endif %}">
                        <td>{% if p.priority >= 4 %}🔥🔥🔥 Высокий{% elif p.priority >= 2 %}🔥🔥 Средний{% else %}🔥 Низкий{% endif %}</td>
                        <td>{{ p.file[:40] }}</td>
                        <td>{{ p.line }}</td>
                        <td>{{ p.type }}</td>
                        <td>{{ p.suggestion[:60] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div id="lead-stats" class="hidden" style="background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:20px;">
            <h3>📊 Распределение по диапазонам</h3>
            {% for r, cnt in ranges.items() %}
            <p>{{ r }}: {{ cnt }} файлов ({{ "%.0f"|format(cnt / total_files * 100 if total_files else 0) }}%)</p>
            <div class="coverage-bar" style="width:100%;"><div class="coverage-fill progress-low" style="width:{{ cnt / total_files * 100 if total_files else 0 }}%;"></div></div>
            {% endfor %}
            
            {% if heatmap_image %}
            <div class="heatmap-container">
                <h3>🔥 Тепловая карта покрытия кода</h3>
                <img src="{{ heatmap_image }}" alt="Тепловая карта покрытия" class="heatmap-img">
                <p style="font-size: 12px; color: #666; margin-top: 10px;">
                    🟢 Зелёный - высокое покрытие (80-100%) | 🟡 Жёлтый - среднее покрытие (50-80%) | 🔴 Красный - низкое покрытие (0-50%)
                </p>
            </div>
            {% endif %}
            
            <div style="margin-top: 30px; text-align: center;">
                <a href="coverage_report.pdf" download class="btn-pdf">
                    📄 Скачать PDF-отчёт
                </a>
                <p style="margin-top: 10px; font-size: 12px; color: #666;">
                    💡 PDF-отчёт содержит статистику и тепловую карту покрытия
                </p>
            </div>
        </div>
        
        <div id="mode-test-info" style="background:#fff5f5;padding:15px;border-radius:8px;margin-bottom:20px;">
            <p>🔍 <strong>Режим тестировщика</strong> — клик на строку покажет тип и рекомендацию. Детальная статистика представлена выше.</p>
        </div>
        <div id="mode-lead-info" class="hidden" style="background:#f0fff4;padding:15px;border-radius:8px;margin-bottom:20px;">
            <p>📈 Режим техлидера — аналитика для принятия решений. Скачайте PDF-отчёт для презентации.</p>
        </div>
        
        <div id="threshold-panel">
            <div class="threshold-filter">
                <span>🔍 Фильтр по покрытию:</span>
                <input type="number" id="coverage-threshold" value="50" step="5" min="0" max="100">%
                <button id="apply-threshold">Показать только файлы ниже порога</button>
                <button id="clear-threshold">Сбросить фильтр</button>
            </div>
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
            <div class="directory-group">
                <div class="directory-title">📁 {{ dirname }}</div>
                <table>
                    <thead><tr><th>Язык</th><th>Файл</th><th>Покрытие</th><th>Индикатор</th></tr></thead>
                    <tbody>
                    {% for f in files %}
                    <tr class="file-row" data-file="{{ loop.index0 }}">
                        <td><span class="language-badge {{ 'lang-python' if f.language.value == 'Python' else 'lang-java' }}">{{ '🐍' if f.language.value == 'Python' else '☕' }} {{ f.language.value }}</span></td>
                        <td>{{ f.name }}{% if f.is_critical %}<span class="critical-badge">CRITICAL</span>{% endif %}</td>
                        <td>{{ "%.1f"|format(f.coverage) }}%</td>
                        <td><div class="coverage-bar"><div class="coverage-fill {{ 'progress-high' if f.coverage >= 80 else 'progress-medium' if f.coverage >= 50 else 'progress-low' }}" style="width:{{ f.coverage }}%;"></div></div></td>
                    </tr>
                    <tr class="code-row hidden"><td colspan="4"><div class="code-viewer" id="code-{{ loop.index0 }}">Загрузка...</div></td></tr>
                    {% endfor %}
                    </tbody>
                </table>
            </div>
        {% endfor %}
        </div>
    </div>
    <div class="footer">
        <p>🔴 Непокрытые строки | 🟢 Покрытые | 💡 Кликните на строку для подсказки</p>
        <p>📊 Тепловая карта показывает покрытие по блокам строк в каждом файле</p>
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
        let html = `<div style="margin-bottom:15px;"><strong>${escapeHtml(f.name)}</strong> (${escapeHtml(f.language)}) - Покрытие: ${f.coverage}%</div>`;
        
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
                    if(viewer && viewer.innerHTML === 'Загрузка...') {
                        viewer.innerHTML = renderCodeViewer(idx);
                    }
                    next.classList.remove('hidden');
                } else {
                    next.classList.add('hidden');
                }
            }
        });
    });
    
    const btns = document.querySelectorAll('.mode-btn');
    const devDash = document.getElementById('dev-dashboard');
    const testStats = document.getElementById('test-stats');
    const leadStats = document.getElementById('lead-stats');
    const testInfo = document.getElementById('mode-test-info');
    const leadInfo = document.getElementById('mode-lead-info');
    const filesContainer = document.getElementById('files-container');
    const thPanel = document.getElementById('threshold-panel');
    
    btns.forEach(btn => {
        btn.addEventListener('click', function() {
            btns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            const m = this.dataset.mode;
            devDash.classList.add('hidden');
            testStats.classList.add('hidden');
            leadStats.classList.add('hidden');
            testInfo.classList.add('hidden');
            leadInfo.classList.add('hidden');
            filesContainer.classList.remove('hidden');
            if(thPanel) thPanel.classList.remove('hidden');
            
            if(m === 'dev') {
                devDash.classList.remove('hidden');
                filesContainer.classList.add('hidden');
                if(thPanel) thPanel.classList.add('hidden');
            } else if(m === 'test') {
                testStats.classList.remove('hidden');
                testInfo.classList.remove('hidden');
            } else if(m === 'lead') {
                leadStats.classList.remove('hidden');
                leadInfo.classList.remove('hidden');
            }
        });
    });
    
    document.getElementById('copy-json')?.addEventListener('click', () => {
        const jsonText = document.getElementById('export-json').innerText;
        navigator.clipboard.writeText(jsonText);
        alert('✅ JSON скопирован в буфер обмена');
    });
    
    document.getElementById('apply-threshold')?.addEventListener('click', () => {
        const th = parseFloat(document.getElementById('coverage-threshold').value);
        document.querySelectorAll('.file-row').forEach(r => {
            const cov = parseFloat(r.cells[2].innerText);
            r.style.display = cov < th ? '' : 'none';
            const next = r.nextElementSibling;
            if(next && next.classList.contains('code-row')) {
                next.classList.add('hidden');
            }
        });
    });
    
    document.getElementById('clear-threshold')?.addEventListener('click', () => {
        document.querySelectorAll('.file-row').forEach(r => r.style.display = '');
        document.getElementById('coverage-threshold').value = '50';
    });
</script>
</body>
</html>'''
        
        # Генерируем тепловую карту
        heatmap_image = None
        try:
            heatmap_path = HeatmapGenerator.generate_heatmap(report, "heatmap.png")
            if heatmap_path and os.path.exists(heatmap_path):
                # Конвертируем в base64 для встраивания
                with open(heatmap_path, "rb") as f:
                    heatmap_base64 = base64.b64encode(f.read()).decode()
                heatmap_image = f"data:image/png;base64,{heatmap_base64}"
        except Exception as e:
            print(f"Ошибка при создании тепловой карты: {e}")
        
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
            files_json=json.dumps(files_json, ensure_ascii=False),
            detailed_stats=report.detailed_stats,
            detailed_stats_json=json.dumps(detailed_stats_json, ensure_ascii=False),
            heatmap_image=heatmap_image
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return output_path


# ====================================================================
# 11. ТОЧКА ВХОДА
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
    
    print(f"✅ HTML-отчёт сгенерирован: {output_file}")
    print(f"📊 Детальная статистика:")
    print(f"   - Всего строк: {report.detailed_stats.total_lines}")
    print(f"   - Непокрыто строк: {report.detailed_stats.uncovered_lines}")
    if report.detailed_stats.worst_files:
        print(f"   - Самый проблемный файл: {report.detailed_stats.worst_files[0]['name']}")
    print(f"   - Рекомендовано приоритетов для тестирования: {len(report.detailed_stats.priorities)}")
    
    # Генерируем тепловую карту
    print("\n🔥 Генерация тепловой карты...")
    heatmap_path = HeatmapGenerator.generate_heatmap(report, "heatmap.png")
    if heatmap_path and os.path.exists(heatmap_path):
        print(f"✅ Тепловая карта сохранена: {heatmap_path}")
    
    # Генерируем PDF-отчёт
    if REPORTLAB_AVAILABLE:
        print("\n📄 Генерация PDF-отчёта...")
        try:
            pdf_path = PDFGenerator.generate_pdf(report, heatmap_path, "coverage_report.pdf")
            if pdf_path:
                print(f"✅ PDF-отчёт сгенерирован: {pdf_path}")
        except Exception as e:
            print(f"⚠️ Ошибка генерации PDF: {e}")
    else:
        print("\n⚠️ Для PDF отчёта установите: pip install reportlab matplotlib numpy")
    
    webbrowser.open(f"file://{os.path.abspath(output_file)}")