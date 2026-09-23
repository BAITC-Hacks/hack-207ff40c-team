import asyncio
import json
import os

import anyio
import httpx

from .store import StoreError, durable_file


class WorkerUnavailable(Exception):
    def __init__(self, message, code="ENGINE_OFFLINE"):
        self.code = code
        super().__init__(message)


class MacClient:
    def __init__(self, settings, transport=None):
        self.client = httpx.AsyncClient(base_url=settings.worker_url,
                                       headers={"Authorization": "Bearer " + settings.worker_token},
                                       timeout=httpx.Timeout(settings.request_timeout, connect=3),
                                       trust_env=False, follow_redirects=False, transport=transport,
                                       verify=settings.worker_tls())

    async def close(self):
        await self.client.aclose()

    def _status(self, response):
        if response.is_redirect:
            raise WorkerUnavailable("Mac worker returned a redirect; refusing to leave the configured private address", "ENGINE_REDIRECT")
        if response.status_code >= 400:
            if response.status_code == 401:
                raise WorkerUnavailable("Mac worker pairing token was rejected; check the station's worker token", "ENGINE_AUTH")
            raise WorkerUnavailable("Mac worker returned HTTP {}; the station archive is preserved".format(response.status_code), "ENGINE_HTTP_" + str(response.status_code))

    async def json(self, method, path, **kwargs):
        try:
            async with self.client.stream(method, path, **kwargs) as response:
                self._status(response)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 16 * 1024 * 1024:
                        raise WorkerUnavailable("Mac worker result exceeds 16 MiB; original audio remains archived", "ENGINE_RESULT_SIZE")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("Expected object")
            return result
        except httpx.TimeoutException as exc:
            raise WorkerUnavailable("Mac worker is not responding; this job is saved on the station and will retry") from exc
        except httpx.RequestError as exc:
            raise WorkerUnavailable("Mac worker is offline; this job is saved on the station and will retry") from exc
        except (ValueError, TypeError) as exc:
            raise WorkerUnavailable("Mac worker returned invalid JSON; archive remains preserved", "ENGINE_INVALID_RESULT") from exc

    async def upload(self, job, source):
        data = {"manifest_json": json.dumps(job["manifest"], ensure_ascii=False)}
        if job["source_kind"] == "audio":
            with source.open("rb") as audio:
                return await self.json("POST", "/v1/jobs", data=data,
                                       files={"audio": (source.name, audio, "application/octet-stream")},
                                       headers={"Idempotency-Key": job["id"]})
        data["transcript"] = await anyio.Path(source).read_text(encoding="utf-8")
        return await self.json("POST", "/v1/jobs", data=data, headers={"Idempotency-Key": job["id"]})

    async def export(self, job_id, format_name, target, revision=None):
        temporary = target.with_suffix(target.suffix + ".partial")
        try:
            params = {"revision": revision} if revision is not None else None
            async with self.client.stream("GET", "/v1/jobs/{}/export/{}".format(job_id, format_name), params=params) as response:
                self._status(response)
                length = 0
                first = b""
                async with await anyio.open_file(temporary, "wb") as output:
                    async for chunk in response.aiter_bytes():
                        if len(first) < 16:
                            first += chunk[:16 - len(first)]
                        length += len(chunk)
                        if length > 64 * 1024 * 1024:
                            raise WorkerUnavailable("Export exceeds the 64 MiB archive limit", "ENGINE_RESULT_SIZE")
                        await output.write(chunk)
            if not length or (format_name == "pdf" and not first.startswith(b"%PDF-")) or (format_name == "docx" and not first.startswith(b"PK\x03\x04")):
                raise WorkerUnavailable("Mac worker produced an empty or invalid export", "ENGINE_INVALID_RESULT")
            os.replace(temporary, target)
            target.chmod(0o600)
            await asyncio.to_thread(durable_file, target)
        except httpx.RequestError as exc:
            raise WorkerUnavailable("Mac worker disconnected while archiving exports; the station will retry") from exc
        finally:
            temporary.unlink(missing_ok=True)


class Worker:
    def __init__(self, store, client, settings):
        self.store, self.client, self.settings = store, client, settings

    async def archive_result(self, job_id, result, *, generation=None):
        if not isinstance(result.get("transcript"), dict) or not isinstance(result.get("protocol"), dict) or result.get("job", {}).get("id") != job_id:
            raise WorkerUnavailable("Worker result failed validation; original audio remains archived", "ENGINE_INVALID_RESULT")
        revision = result.get("review_revision", 0)
        if type(revision) is not int or revision < 0:
            raise WorkerUnavailable("Invalid report revision", "ENGINE_INVALID_RESULT")
        directory = self.store.exports / job_id
        if revision:
            directory /= "review-{}".format(revision)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        formats = ["json", "csv", "pdf", "ics"]
        if "docx" in result.get("exports", {}):
            formats.append("docx")
        for format_name in formats:
            # Older workers do not have review revisions. New workers must keep
            # every downloaded file on the same revision as the cached report.
            kwargs = {"revision": revision} if "review_revision" in result else {}
            await self.client.export(job_id, format_name, directory / ("meeting." + format_name), **kwargs)
        self.store.complete(job_id, result, generation=generation)

    async def run_once(self):
        row = self.store.work()
        if row is None:
            return False
        job_id = row["id"]
        job = json.loads(row["payload"])
        checking_existing = bool(row["submitted"] or row["action"])
        generation = row['generation']
        try:
            if row["action"]:
                try:
                    remote = await self.client.json("POST", "/v1/jobs/{}/{}".format(job_id, row["action"]))
                except WorkerUnavailable as exc:
                    if row["action"] != "retry" or exc.code != "ENGINE_HTTP_409":
                        raise
                    # Retry can race an undelivered cancellation or a completed
                    # Mac job whose exports are still being archived here.
                    # In either case the existing Mac job can satisfy the retry.
                    remote = await self.client.json("GET", "/v1/jobs/" + job_id)
                    if remote.get('stage') in {'cancelled', 'failed'}:
                        # The worker refuses retry until the old inference exits.
                        # A terminal snapshot is not an acknowledgement of the
                        # new request: keep the durable retry command pending.
                        raise WorkerUnavailable('Waiting for the previous worker attempt to exit; retry remains queued', 'ENGINE_RETRY_PENDING')
            elif not row["submitted"]:
                remote = await self.client.upload(job, self.store.source(job_id))
            else:
                remote = await self.client.json("GET", "/v1/jobs/" + job_id)
            if not self.store.apply_remote(job_id, remote, delay=self.settings.poll_seconds, generation=generation):
                return True
            checking_existing = False
            if remote.get("stage") == "completed" and self.store.get(job_id)["stage"] != "cancelled":
                result = await self.client.json("GET", "/v1/jobs/{}/result".format(job_id))
                await self.archive_result(job_id, result, generation=generation)
        except asyncio.CancelledError:
            raise
        except WorkerUnavailable as exc:
            if checking_existing and exc.code == "ENGINE_HTTP_404":
                self.store.remote_missing(job_id, generation=generation)
            else:
                terminal = not row['submitted'] and not row['action'] and exc.code in {'ENGINE_HTTP_400', 'ENGINE_HTTP_409', 'ENGINE_HTTP_413', 'ENGINE_HTTP_415', 'ENGINE_HTTP_422'}
                self.store.defer(job_id, str(exc), exc.code, generation=generation, terminal=terminal)
        except Exception as exc:
            # Do not reflect model output, transcript, credentials or filesystem paths in errors.
            self.store.defer(job_id, "Station processing needs attention ({}); archived source is preserved".format(type(exc).__name__), "STATION_ERROR", generation=generation)
        return True

    async def run(self):
        while True:
            if not await self.run_once():
                await asyncio.sleep(min(self.settings.poll_seconds, 0.5))
