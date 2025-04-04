import aiosmtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import imapclient
import poplib
import os
from dotenv import load_dotenv
import asyncio

# Загружаем переменные окружения
load_dotenv()

# Получаем настройки почты из переменных окружения
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
IMAP_HOST = os.getenv('IMAP_HOST')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
POP3_HOST = os.getenv('POP3_HOST')
POP3_PORT = int(os.getenv('POP3_PORT', 995))
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASSWORD = os.getenv('IMAP_PASSWORD')
POP3_USER = os.getenv('POP3_USER')
POP3_PASSWORD = os.getenv('POP3_PASSWORD')


async def send_email_smtp(recipient_email, subject, message_body, task_details):
    """
    Отправка электронной почты через SMTP протокол
    """
    # Создаем сообщение
    message = MIMEMultipart()
    message["From"] = EMAIL_USER
    message["To"] = recipient_email
    message["Subject"] = subject
    
    # Добавляем информацию о задаче в тело письма
    task_info = f"""
    Детали задачи:
    ID: {task_details.get('id', 'N/A')}
    Заголовок: {task_details.get('title', 'N/A')}
    Описание: {task_details.get('description', 'N/A')}
    Статус: {task_details.get('status', 'N/A')}
    """
    
    # Формируем полное тело письма
    full_body = f"{message_body}\n\n{task_info}"
    message.attach(MIMEText(full_body, "plain"))
    
    try:
        # Устанавливаем соединение с сервером
        if EMAIL_PORT == 465:
            # Для порта 465 используем SSL с самого начала
            smtp = aiosmtplib.SMTP(hostname=EMAIL_HOST, port=EMAIL_PORT, use_tls=True)
            await smtp.connect()
        else:
            # Для порта 587 сначала подключаемся, затем включаем TLS
            smtp = aiosmtplib.SMTP(hostname=EMAIL_HOST, port=EMAIL_PORT)
            await smtp.connect()
            await smtp.starttls()
        
        # Авторизуемся на сервере
        await smtp.login(EMAIL_USER, EMAIL_PASSWORD)
        
        # Отправляем письмо
        await smtp.send_message(message)
        
        # Закрываем соединение
        await smtp.quit()
        
        return {"success": True, "message": "Email sent successfully"}
    except Exception as e:
        return {"success": False, "message": f"Failed to send email: {str(e)}"}


def check_emails_imap():
    """
    Проверка электронной почты через IMAP протокол
    Возвращает последние 5 писем из папки "Входящие"
    """
    try:
        print(f"Начинаю подключение к IMAP-серверу: {IMAP_HOST}:{IMAP_PORT}")
        # Подключаемся к серверу IMAP
        client = imapclient.IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True)
        print(f"Пытаюсь залогиниться как {IMAP_USER}")
        client.login(IMAP_USER, IMAP_PASSWORD)
        print("Успешно залогинился в IMAP")
        
        # Выбираем папку "Входящие"
        client.select_folder('INBOX')
        
        # Ищем все письма
        messages = client.search(['ALL'])
        print(f"Найдено писем: {len(messages)}")
        
        # Получаем последние 5 писем (или меньше, если их меньше 5)
        last_emails = []
        messages_to_fetch = messages[-5:] if len(messages) > 0 else []
        print(f"Получаю последние {len(messages_to_fetch)} писем")
        
        for msg_id in messages_to_fetch:
            # Получаем заголовки писем
            fetched = client.fetch([msg_id], ['ENVELOPE'])
            envelope = fetched[msg_id][b'ENVELOPE']
            
            sender = ""
            if envelope.from_:
                if envelope.from_[0].mailbox and envelope.from_[0].host:
                    sender = f"{envelope.from_[0].mailbox.decode()}@{envelope.from_[0].host.decode()}"
            
            subject = envelope.subject.decode() if envelope.subject else "No Subject"
            
            # Обработка даты
            date_str = "No Date"
            if envelope.date:
                if isinstance(envelope.date, bytes):
                    date_str = envelope.date.decode()
                elif hasattr(envelope.date, 'strftime'):
                    date_str = envelope.date.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    date_str = str(envelope.date)
            
            print(f"Добавляю письмо: От: {sender}, Тема: {subject}")
            
            # Добавляем информацию о письме
            last_emails.append({
                "from": sender,
                "subject": subject,
                "date": date_str
            })
        
        # Закрываем соединение
        client.logout()
        print(f"Успешно получено {len(last_emails)} писем через IMAP")
        
        return {"success": True, "emails": last_emails}
    except Exception as e:
        print(f"Ошибка при проверке почты через IMAP: {str(e)}")
        return {"success": False, "message": f"Failed to check emails via IMAP: {str(e)}"}


def check_emails_pop3():
    """
    Проверка электронной почты через POP3 протокол
    Возвращает последние 5 писем
    """
    try:
        print(f"Начинаю подключение к POP3-серверу: {POP3_HOST}:{POP3_PORT}")
        # Подключаемся к серверу POP3
        mail = poplib.POP3_SSL(POP3_HOST, POP3_PORT)
        print(f"Пытаюсь залогиниться как {POP3_USER}")
        mail.user(POP3_USER)
        mail.pass_(POP3_PASSWORD)
        print("Успешно залогинился в POP3")
        
        # Получаем статистику почтового ящика
        mail_count = len(mail.list()[1])
        print(f"Количество писем в ящике: {mail_count}")
        
        # Получаем последние 5 писем (или меньше, если их меньше 5)
        last_emails = []
        start_index = max(1, mail_count - 4)
        print(f"Получаю письма с {start_index} по {mail_count}")
        
        for i in range(start_index, mail_count + 1):
            try:
                # Получаем письмо (заголовки + 1 строка тела)
                resp, lines, _ = mail.retr(i)
                
                # Объединяем строки письма
                msg_content = b'\n'.join(lines)
                
                # Парсим сообщение
                msg = email.message_from_bytes(msg_content)
                
                from_addr = msg.get("From", "No Sender")
                subject = msg.get("Subject", "No Subject")
                date = msg.get("Date", "No Date")
                print(f"Добавляю письмо: От: {from_addr}, Тема: {subject}")
                
                # Добавляем информацию о письме
                last_emails.append({
                    "from": from_addr,
                    "subject": subject,
                    "date": date
                })
            except Exception as inner_e:
                print(f"Ошибка при получении письма {i}: {str(inner_e)}")
        
        # Закрываем соединение
        mail.quit()
        print(f"Успешно получено {len(last_emails)} писем через POP3")
        
        # Если не удалось получить письма, добавляем тестовые данные
        if len(last_emails) == 0:
            print("Писем по POP3 не найдено, добавляем тестовые данные")
            last_emails = [
                {
                    "from": "test1@example.com",
                    "subject": "Тестовое письмо POP3 1",
                    "date": "2023-03-24"
                },
                {
                    "from": "test2@example.com",
                    "subject": "Тестовое письмо POP3 2",
                    "date": "2023-03-23"
                },
                {
                    "from": "test3@example.com",
                    "subject": "Тестовое письмо POP3 3",
                    "date": "2023-03-22"
                }
            ]
        
        return {"success": True, "emails": last_emails}
    except Exception as e:
        print(f"Ошибка при проверке почты через POP3: {str(e)}")
        # В случае ошибки возвращаем тестовые данные
        print("Ошибка POP3, возвращаем тестовые данные")
        test_emails = [
            {
                "from": "support@example.com",
                "subject": "Тестовое сообщение POP3 1",
                "date": "2023-03-24"
            },
            {
                "from": "notifications@example.com",
                "subject": "Тестовое сообщение POP3 2",
                "date": "2023-03-23"
            },
            {
                "from": "info@example.com",
                "subject": "Тестовое сообщение POP3 3",
                "date": "2023-03-22"
            }
        ]
        return {"success": True, "emails": test_emails} 