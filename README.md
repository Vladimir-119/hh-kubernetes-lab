# Расчёт пар навыков в Kubernetes

Домашнее задание 5 по дисциплине «Инженерия данных».

Автор: Волков Владимир Алексеевич, группа J3313.
Вариант из ДЗ 3: программист C/C++.

## Результаты

- Kubernetes развёрнут локально через Minikube, профиль de-k8s.
- Собран Docker-образ hh-pairs:lab.
- При пределе памяти 12Mi получен OOMKilled.
- По измеренному пику выбран предел 32Mi; повторный запуск успешен.
- RustFS развёрнут внутри кластера с Service и PVC.
- Четыре части файла обработаны Indexed Job с parallelism: 2.
- Объединённый CSV полностью совпал с результатом ДЗ 3.
- Проверены ожидание CPU, вытеснение по приоритету и ResourceQuota.

Обработано 68 770 строк, отобрано 869 вакансий.
Получено 6 800 различных пар и 13 468 вхождений.

## Файлы

- Dockerfile и requirements.txt — сборка образа.
- worker.py и source_tools.py — расчёт пар и фильтр варианта.
- create_s3_secret.py — создание Secret из локальных настроек.
- upload_s3_data.py — разбиение и загрузка данных в S3.
- collect_parallel.py — сбор журналов параллельных воркеров.
- finish_parallel_check.py — объединение и полная сверка результатов.
- k8s/ — манифесты Kubernetes.
- logs/ — журналы выполненных запусков.
- evidence/ — машинно-читаемые подтверждения.
- reference/counts_k2.csv — эталон ДЗ 3.
- results/parallel.csv — объединённый результат.
- data/it_vacancies.jsonl — исходные данные для сборки образа.

## Отчёт

[Отчёт в PDF](Volkov_Kubernetes_HW5_report.pdf)

В отчёте приведены настройки стенда, порядок экспериментов,
скриншоты, обоснование предела памяти и сравнение YARN, Mesos и Kubernetes.

## Проверка результата

Финальная сверка сохранена в logs/44-parallel-verification.txt
и evidence/parallel-verification.json.

Все проверки успешны:
full_counts_equal, full_csv_bytes_equal и top10_equal.

## Зависимости локальных скриптов

Python 3.12, kubectl, Docker и Minikube.
Python-зависимости: requirements.txt и python-dotenv.
Параметры доступа S3 задаются в локальном .env.
