import sys
import time
from http import HTTPStatus
from logging import StreamHandler

import requests
import os
import logging

from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = ('https:'
            '//practicum.yandex.ru/api/user_api/homework_statuses/')
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

# я бы с радостью убрал бы в main() но тогда меня тесты не пускают
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s -%(message)s')
file_handler = logging.FileHandler(
    'program.log', mode='w')
file_handler.setFormatter(formatter)
stream_handler = StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


class APIRequestStatusError(RuntimeError):
    def __init__(self, message, error_code=None):
        self.message = message
        self.error_code = error_code
        super().__init__(f'{message} (Код ошибки: {error_code}')


def check_tokens():
    """
    Проверяет, что все необходимые токены окружения присутствуют.

    Убедитесь, что переменные PRACTICUM_TOKEN,
    TELEGRAM_TOKEN и TELEGRAM_CHAT_ID
    установлены в окружении. В случае отсутствия хотя бы одной
    из переменных, будет залогирована критическая ошибка,
    и вызвано исключение ValueError.

    :raises ValueError: если отсутствует хотя бы одна из
    переменных окружения.
    """

    if not PRACTICUM_TOKEN:
        raise ValueError('Отсутствует токен PRACTICUM_TOKEN')

    if not TELEGRAM_TOKEN:
        raise ValueError('Отсутствует токен TELEGRAM_TOKEN')

    if not TELEGRAM_CHAT_ID:
        raise ValueError('Отсутствует токен TELEGRAM_CHAT_ID')


def get_api_answer(timestamp: int):
    """
    Получает ответ от API сервиса Практикум.

    Отправляет GET-запрос к API с заданной временной меткой,
    чтобы получить информацию о статусах домашних работ.
    При успешном запросе возвращает ответ в формате JSON.

    :param timestamp: Временная метка в формате Unix Time.
    :return: Ответ API в формате JSON.
    :raises TypeError: если timestamp не является целым числом.
    :raises ValueError: если API недоступен
    или произошла ошибка запроса.
    """

    if not isinstance(timestamp, int):
        raise TypeError(
            f'Время: {timestamp} - должно быть в формате Unix Time')

    payload = {'from_date': timestamp}
    try:
        api_answer = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload)

    except requests.RequestException as Error:
        raise ValueError(f'Непредвиденная ошибка {Error}')

    if api_answer.status_code != HTTPStatus.OK:
        raise APIRequestStatusError(
            f'Ответ API сервера != {HTTPStatus.OK}',
            error_code=api_answer.status_code)

    return api_answer.json()


def check_response(response):
    """
    Проверяет правильность структуры ответа API.

    Убедитесь, что ответ API является корректным словарём и содержит
    необходимые ключи, включая список под ключом 'homeworks'.

    :param response: Ответ API, преобразованный в словарь.
    :return: Список домашних работ.
    :raises TypeError: если response не является словарём или
        'homeworks' не является списком.
    :raises KeyError: если отсутствует ключ 'homeworks' в response.
    """

    if not isinstance(response, dict):
        raise TypeError(
            f'Response от API должен быть словарем,'
            f' а содержит {type(response)}')

    if 'homeworks' not in response:
        raise KeyError(
            'В ответе отсутствует ключ "homeworks"!')

    if not isinstance(response['homeworks'], list):
        raise TypeError(
            f'Ключ Homeworks должен содержать список list, '
            f'а содержит {type(response["homeworks"])}')

    return response['homeworks']


def parse_status(homework):
    """
    Извлекает статус конкретной домашней работы из ответа API.

    Получает элемент из списка домашних работ, извлекает
    название и статус работы, сопоставляет статус с вердиктом
    из словаря HOMEWORK_VERDICTS и формирует строку для отправки
    в Telegram.

    :param homework: Один элемент из списка домашних работ.
    :return: Строка с названием работы и её статусом.
    :raises KeyError: если в homework отсутствуют ключи 'homework_name'
    или 'status'.
    :raises ValueError: если статус домашней работы не задокументирован.
    """
    valid_statuses = ['approved',
                      'rejected',
                      'pending',
                      'reviewing']

    if 'homework_name' not in homework:
        raise KeyError(
            'Отсутствует ключ "homework_name" в домашней работе!')

    try:
        status = homework['status']
    except KeyError:
        raise KeyError(
            'Статус домашней работы отсутствует')

    if status not in valid_statuses:
        raise ValueError(
            f'Недокументированный статус: {status}')

    homework_name = homework['homework_name']

    verdict = HOMEWORK_VERDICTS.get(status)

    return (f'Изменился статус проверки работы'
            f' "{homework_name}". {verdict}')


def send_message(bot, message):
    """
    Отправляет сообщение в Telegram-чат.

    Использует экземпляр класса TeleBot для отправки
    сообщения с заданным текстом в чат, определённый
    переменной окружения TELEGRAM_CHAT_ID.

    :param bot: Экземпляр класса TeleBot.
    :param message: Текст сообщения для отправки.
    :raises Exception: если возникла ошибка при отправке сообщения.
    """
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(
            f'Сообщение {message} успешно отправлено')
    except requests.exceptions.RequestException as Erors:
        raise requests.exceptions.RequestException(
            f'Ошибка {Erors} при отправке сообщения')

def main():
    """
    Основной алгоритм работы бота.

    В этой функции реализована логика работы программы:
    1. Проверка наличия токенов.
    2. Запрос к API.
    3. Проверка ответа от API.
    4. Извлечение статусов домашних работ
    и отправка уведомлений в Telegram.
    5. Бесконечный цикл с интервалом ожидания RETRY_PERIOD.
    """

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    logger.info('Запускаем бота...вжух#')

    while True:
        try:

            try:
                check_tokens()
                logger.info('Все токены доступны')
            except ValueError as error:
                logger.critical(error)
                sys.exit()
                # Завершаем программу, если токены отсутствуют

            response_api = get_api_answer(timestamp)
            logger.debug(f'Ответ API получен: {response_api}')

            timestamp = response_api.get('current_date', timestamp)

            homeworks = check_response(response_api)
            logger.debug(f'Ответ от API содержит {homeworks}')

            if not homeworks:
                logger.debug(
                    'Список домашних работ пуст — статус не изменился.')

            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)

                    if message != last_message:
                        send_message(bot=bot, message=message)
                        logger.debug(
                            f'Сообщение {message} успешно отправлено')
                        last_message = message
                    else:
                        logger.debug(
                            'Сообщение совпадает с предыдущим отправленным')

        except Exception as error:
            logger.error(
                f'Ошибка в работе программы: {error}')

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
