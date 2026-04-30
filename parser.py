# Импортируем модуль для работы с XML-файлами (встроен в Python)
import xml.etree.ElementTree as ET

# Определяем функцию, которая принимает путь к файлу coverage.xml
def parse_coverage_xml(file_path):
    # Загружаем XML-файл и парсим его в дерево элементов
    tree = ET.parse(file_path)
    # Получаем корневой элемент (<coverage>)
    root = tree.getroot()
    
    # Выводим заголовок таблицы
    print("Файлы и покрытие строк:")
    print("-" * 40)  # 40 символов "минус" для разделителя
    
    # Ищем все элементы <package> (пакеты), а внутри них — <class> (классы/файлы)
    # .findall('.//package') — ищет на любом уровне вложенности
    for package in root.findall('.//package'):
        for class_elem in package.findall('.//class'):
            # Получаем имя файла из атрибута filename
            filename = class_elem.get('filename')
            # Пропускаем файлы, у которых нет имени или это не Python-файл
            if not filename or not filename.endswith('.py'):
                continue
                
            # Находим все строки (<line>) внутри текущего класса
            lines = class_elem.findall('.//line')
            # Общее количество строк = длина списка
            total_lines = len(lines)
            # Считаем покрытые строки: у которых атрибут hits не равен '0'
            covered_lines = sum(1 for line in lines if line.get('hits') != '0')
            # Вычисляем процент покрытия (избегаем деления на ноль)
            coverage = (covered_lines / total_lines * 100) if total_lines > 0 else 0
            
            # Выводим результат для каждого файла
            # :.1f — форматирование с одним знаком после запятой
            # :.0f — целое число без знаков после запятой
            print(f"{filename}: {coverage:.1f}% ({covered_lines:.0f}/{total_lines})")

# Точка входа в программу: этот код выполнится, только если файл запущен напрямую
# (а не импортирован как модуль)
if __name__ == "__main__":
    # Вызываем нашу функцию с именем файла coverage.xml
    parse_coverage_xml("coverage.xml")