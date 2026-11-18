"""Замер скорости скачивания: 10 последовательных запросов к одному URL."""

import argparse
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REQUEST_COUNT = 10
DEFAULT_TIMEOUT_SECONDS = 30
CHUNK_SIZE_BYTES = 64 * 1024
BYTES_PER_KB = 1_000
BYTES_PER_MB = 1_000_000
BITS_PER_BYTE = 8
BITS_PER_MBIT = 1_000_000
USER_AGENT = "internet-speed-test/1.0 (+python-urllib)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Скачивает URL {REQUEST_COUNT} раз подряд и считает скорость скачивания.",
    )
    parser.add_argument("url", nargs="?", help="адрес файла (http/https); если не указан — будет запрошен")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"таймаут сетевых операций в секундах (по умолчанию {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="не делать прогревочный запрос перед замером",
    )
    return parser.parse_args()


def validate_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"некорректный URL «{url}»: нужен адрес вида http(s)://host/path")
    return url


def fetch_once(url: str, timeout: float) -> tuple[int, int, str, float]:
    """Скачивает тело ответа полностью. Возвращает (байты, HTTP-код, статус, секунды)."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    total_bytes = 0
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        while chunk := response.read(CHUNK_SIZE_BYTES):
            total_bytes += len(chunk)
    elapsed = time.perf_counter() - started
    return total_bytes, response.status, response.reason, elapsed


def to_mb(n_bytes: float) -> float:
    return n_bytes / BYTES_PER_MB


def format_size(n_bytes: int) -> str:
    if n_bytes < BYTES_PER_MB:
        return f"{n_bytes / BYTES_PER_KB:.1f} КБ"
    return f"{to_mb(n_bytes):.2f} МБ"


def to_mbit_per_s(n_bytes: float, seconds: float) -> float:
    # байты -> биты, затем в мегабиты (десятичные, 10^6)
    return n_bytes * BITS_PER_BYTE / seconds / BITS_PER_MBIT


def run(url: str, timeout: float, warmup: bool) -> None:
    print(f"URL: {url}")
    if warmup:
        size, code, reason, seconds = fetch_once(url, timeout)
        print(f"прогрев: {code} {reason}, {format_size(size)}, {seconds:.2f} с (не учитывается)")

    sizes: list[int] = []
    durations: list[float] = []
    for attempt in range(1, REQUEST_COUNT + 1):
        size, code, reason, seconds = fetch_once(url, timeout)
        sizes.append(size)
        durations.append(seconds)
        print(f"#{attempt:<2} {code} {reason}, {format_size(size)}, {seconds:.2f} с")

    total_bytes = sum(sizes)
    total_seconds = sum(durations)
    avg_seconds = total_seconds / len(durations)
    mbps = to_mbit_per_s(total_bytes, total_seconds)
    mb_per_s = to_mb(total_bytes) / total_seconds

    print()
    print(f"Запросов:                {len(durations)}")
    print(f"Среднее время запроса:   {avg_seconds:.3f} с")
    print(f"Всего скачано:           {format_size(total_bytes)} ({total_bytes} байт)")
    print(f"Скорость скачивания:     {mbps:.2f} Мбит/с ({mb_per_s:.2f} МБ/с)")


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    try:
        raw_url = args.url if args.url else input("Введите URL: ")
        url = validate_url(raw_url)
        if args.timeout <= 0:
            raise ValueError("таймаут должен быть больше нуля")
        run(url, args.timeout, warmup=not args.no_warmup)
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2
    except HTTPError as error:
        print(f"Ошибка: сервер ответил {error.code} {error.reason}", file=sys.stderr)
        return 1
    except URLError as error:
        print(f"Ошибка сети: {error.reason}", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"Ошибка: превышен таймаут {args.timeout:g} с", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Ошибка соединения: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nПрервано пользователем.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
