# ==================== ПАРСЕР jacoco.xml (Java) ====================
# Назначение: читает отчёт JaCoCo и выводит в консоль статистику покрытия для Java-файлов

# Импортируем модуль для работы с XML-файлами (встроен в Python)
import xml.etree.ElementTree as ET

def parse_jacoco_xml(file_path):
    """
    Парсер отчёта JaCoCo (упрощённая версия, без пространства имён)
    Аргумент: file_path - путь к файлу jacoco.xml
    Результат: печатает в консоль список Java-файлов с процентом покрытия инструкций
    """
    
    # ET.parse() открывает XML-файл и превращает его в дерево объектов
    # Если файл не найден или не является корректным XML — будет ошибка
    tree = ET.parse(file_path)
    
    # tree.getroot() возвращает корневой элемент документа
    # У JaCoCo корневой элемент называется <report>
    root = tree.getroot()
    
    # Печатаем заголовок таблицы в консоль
    print("Java-файлы и покрытие инструкций:")
    print("-" * 50)  # печатает 50 дефисов как разделитель
    
    # root.findall('.//sourcefile') — ищет ВСЕ элементы <sourcefile> на любом уровне вложенности
    # Точки с двойным слешем означают «в любом месте документа»
    for sourcefile in root.findall('.//sourcefile'):
        
        # .get('name') берёт значение атрибута name у тега <sourcefile>
        # Обычно там хранится имя файла, например "Main.java"
        filename = sourcefile.get('name')
        
        # Пропускаем строки, если нет имени файла или это не Java-файл
        # endswith('.java') проверяет окончание строки
        if not filename or not filename.endswith('.java'):
            continue   # переходим к следующему файлу
        
        # Ищем внутри текущего <sourcefile> тег <counter> с типом INSTRUCTION
        # [@type="INSTRUCTION"] — это условие: атрибут type должен равняться "INSTRUCTION"
        # Инструкции — это базовые единицы байт-кода Java (более точная метрика, чем строки)
        counter = sourcefile.find('.//counter[@type="INSTRUCTION"]')
        
        # Если такой счётчик найден — извлекаем данные
        if counter is not None:
            # int(counter.get('covered')) — получаем количество покрытых инструкций и преобразуем в число
            # int(counter.get('missed')) — получаем количество пропущенных инструкций
            covered = int(counter.get('covered'))
            missed = int(counter.get('missed'))
            
            # total = сумма покрытых и пропущенных = все инструкции в файле
            total = covered + missed
            
            # Вычисляем процент покрытия
            # (covered / total) * 100 — формула процентов
            # if total > 0 — защита от деления на ноль (на случай, если файл пустой)
            coverage = (covered / total * 100) if total > 0 else 0
            
            # Выводим результат для очередного файла
            # :.1f — округлить до 1 знака после запятой (например 75.0%)
            # {covered}/{total} — показывает количество покрытых инструкций из общего числа
            print(f"{filename}: {coverage:.1f}% ({covered}/{total})")

# ==================== ТОЧКА ВХОДА ====================
# Эта конструкция означает: запускать код только если файл выполняется как основная программа
# Если этот файл импортировать как модуль (import javaparser) — код НЕ выполнится
if __name__ == "__main__":
    # Запускаем нашу функцию и передаём ей имя файла jacoco.xml
    parse_jacoco_xml("jacoco.xml")