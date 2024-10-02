import time
from http import HTTPStatus
from logging import StreamHandler

import requests
import os
import logging

from dotenv import load_dotenv
from telebot import TeleBot, logger

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

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    filename='program.log',
    filemode='w'
)
handler = StreamHandler()
logger.addHandler(handler)


def check_tokens():
    """
    Проверяет наличие всех необходимых переменных окружения.

    Проверяет, что переменные PRACTICUM_TOKEN,
    TELEGRAM_TOKEN и TELEGRAM_CHAT_ID
    доступны в окружении.
    Если хотя бы одна из переменных отсутствует,
    логирует критическую ошибку
    и выбрасывает исключение ValueError.

    :raises ValueError: если одна из переменных окружения отсутствует.
    """
    try:
        if not (PRACTICUM_TOKEN
                and TELEGRAM_TOKEN
                and TELEGRAM_CHAT_ID):
            logger.critical(
                'Проверьте правильность заполнения токена')
            raise ValueError(
                'Проверьте правильность заполнения токена')

    except Exception as Error:
        logger.error(f"Произошла ошибка: {Error}")
        print(f"Произошла ошибка: {Error}")
        raise


def get_api_answer(timestamp: int):
    """
    Делает запрос к API сервиса Практикум Домашка.

    Отправляет GET-запрос к API
    с временной меткой для получения информации
    о статусах домашних работ.
    Если запрос прошёл успешно, возвращает
    ответ в формате JSON.

    :param timestamp: временная метка в формате Unix Time.
    :return: ответ API в формате JSON.
    :raises TypeError: если timestamp передан не в формате int.
    :raises ValueError: если API
    недоступен или произошла ошибка запроса.
    """
    if not ENDPOINT and HEADERS:
        logger.error(
            'Отсутствие ожидаемых ключей в ответе API ')
        raise ValueError(
            'необходимые значения отстствуют')

    if not isinstance(timestamp, int):
        logger.error(
            f'Время указано в формате {timestamp}, '
            'а должно быть int')
        raise TypeError(
            'Время должно быть в формате Unix Time')

    payload = {'from_date': timestamp}
    try:
        api_answer = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload)

        if api_answer.status_code != HTTPStatus.OK:
            logger.error(
                'Ендпоинт недоступен')
            raise ValueError(
                'Проверьте правильность заполнения токена '
                'или состояние сервера')

    except requests.RequestException as Error:
        logger.error(f'Непредвиденная ошибка {Error}')
        raise ValueError(f'Непредвиденная ошибка {Error}')

    return api_answer.json()


def check_response(response):
    """
    Проверяет корректность ответа API.

    Проверяет, что ответ API
    содержит необходимые ключи и является корректным
    словарём. Также проверяет,
    что ключ 'homeworks' содержит список.

    :param response: ответ API,
    приведённый к типам данных Python.
    :return: список домашних работ.
    :raises TypeError: если response не является словарём или
        'homeworks' не является списком.
    :raises KeyError: если ключ 'homeworks' отсутствует в response.
    """
    if not isinstance(response, dict):
        logger.debug(
            'Response от API должен быть словарем!')
        raise TypeError(
            'Response от API должен быть словарем!')

    if 'homeworks' not in response:
        logger.debug(
            'В ответе отсутствует ключ "homeworks"!')
        raise KeyError(
            'В ответе отсутствует ключ "homeworks"!')

    if not isinstance(response['homeworks'], list):
        logger.debug(
            'Ключ Homeworks должен содержать список list')
        raise TypeError(
            'Ключ Homeworks должен содержать список list')

    if not response['homeworks']:
        logger.debug(
            'Список домашних работ пуст — статус не изменился.')

    return response['homeworks']


def parse_status(homework):
    """
    Извлекает статус домашней работы из ответа API.

    Получает на вход один элемент
    из списка домашних работ, извлекает
    название работы и её статус, сопоставляет статус с вердиктом из
    словаря HOMEWORK_VERDICTS и
    формирует строку для отправки в Telegram.

    :param homework: один элемент
    из списка домашних работ.
    :return: строка с названием работы и её статусом.
    :raises KeyError: если в homework
    отсутствуют ключи 'homework_name' или 'status'.
    :raises ValueError: если статус домашней работы
    не задокументирован.
    """
    if not homework:
        logger.debug('Список домашних работ пуст')
        return

    if ('homework_name' not in homework
            or 'status' not in homework):
        logger.error('Неожиданный статус домашней работы,'
                     ' обнаруженный в ответе API ')
        raise KeyError('Необходимых ключей нет!')

    try:
        status = homework['status']
    except KeyError:
        raise KeyError(
            'Стутус домашней работы отсутсвует')

    valid_statuses = ['approved',
                      'rejected',
                      'pending',
                      'reviewing']
    if status not in valid_statuses:
        raise ValueError(
            f'Недокументированный статус: {status}')

    homework_name = homework['homework_name']

    verdict = None
    for key, value in HOMEWORK_VERDICTS.items():
        if key in homework['status']:
            verdict = value
            break
    return (f'Изменился статус проверки работы'
            f' "{homework_name}". {verdict}')


def send_message(bot, message):
    """
    Отправляет сообщение в Telegram-чат.

    Использует экземпляр класса
    TeleBot для отправки сообщения с текстом
    message в чат, определённый
    переменной окружения TELEGRAM_CHAT_ID.

    :param bot: экземпляр класса TeleBot.
    :param message: текст сообщения для отправки.
    :raises Exception: если произошла ошибка при
    отправке сообщения.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение {message} успешно отправлено')
    except requests.exceptions.RequestException as Erors:
        logger.error(f'Ошибка {Erors}при отправке сообщения')
    except Exception as Error:
        logger.error(f'Непредвиденная ошибка {Error} '
                     f'при отправке сообщения')


def main():
    """
    Основная логика работы бота.

    В этой функции описана основная логика работы программы:
    1. Проверяет наличие токенов.
    2. Делает запрос к API.
    3. Проверяет ответ от API.
    4. Извлекает статус домашних работ
    и отправляет уведомления в Telegram.
    5. Работает в бесконечном цикле
     с интервалом ожидания RETRY_PERIOD.
    """
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            check_tokens()
            response_api = get_api_answer(timestamp)
            homeworks = check_response(response_api)

            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot=bot, message=message)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            print(message)
            raise

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
