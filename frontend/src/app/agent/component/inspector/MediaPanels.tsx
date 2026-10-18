import { useState } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../../../component/Icon";
import {
  getGetMediaContentUrl,
  useGetMedia,
} from "../../../generated-apis-types/media/media";
import { formatNumber, truncate } from "../../../../lib/format";
import {
  excerptOf,
  numberField,
  recordId,
  recordList,
  safeResourceUrl,
  stringList,
  textField,
} from "../../trace";
import {
  InspectorMediaStage,
  LivePanel,
  PanelEmpty,
  PanelLink,
  type PanelProps,
} from "./common";

interface MediaHit {
  readonly record: Record<string, unknown>;
  readonly id: number | null;
  readonly title: string;
  readonly excerpt: string;
  readonly width: number | null;
  readonly height: number | null;
  readonly tags: readonly string[];
  readonly href: string | null;
}

function hitsOf(data: Record<string, unknown> | null): MediaHit[] {
  return recordList(data?.results).map((record) => {
    const id = recordId(record, "media_id");
    const path = textField(record, "raw_file_path") ?? "";
    const title =
      textField(record, "title") ??
      textField(record, "file_name") ??
      (path.split("/").filter(Boolean).at(-1) ?? `media ${id ?? "?"}`);
    return {
      record,
      id,
      title,
      excerpt: excerptOf(record, ["excerpt", "caption", "summary", "ocr_text"], 220),
      width: numberField(record, "width"),
      height: numberField(record, "height"),
      tags: stringList(record.tags),
      href: safeResourceUrl(
        record.viewer_url,
        id === null ? null : { type: "media", id, chunk: null, title },
      ),
    };
  });
}

function ContactSheet({ hits }: { readonly hits: readonly MediaHit[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(hits[0]?.id ?? null);
  const selected = hits.find((hit) => hit.id === selectedId) ?? hits[0] ?? null;

  if (hits.length === 0) {
    return (
      <PanelEmpty
        icon="ring"
        title="No specimens in this pass"
        detail="The media query returned no image results."
      />
    );
  }

  return (
    <div className="pi-contact-sheet">
      {selected?.id !== null && selected?.id !== undefined ? (
        <div className="pi-contact-sheet__preview">
          <img
            src={getGetMediaContentUrl(selected.id)}
            alt={selected.title}
            loading="lazy"
            decoding="async"
          />
          <div className="pi-contact-sheet__preview-copy">
            <strong>{selected.title}</strong>
            {selected.excerpt ? <p>{selected.excerpt}</p> : null}
            {selected.href ? <PanelLink to={selected.href}>Open specimen</PanelLink> : null}
          </div>
        </div>
      ) : null}

      <ul className="pi-contact-sheet__grid">
        {hits.map((hit, index) => (
          <li key={hit.id ?? index}>
            <button
              type="button"
              className={hit.id === selectedId ? "pi-contact-sheet__frame is-selected" : "pi-contact-sheet__frame"}
              onClick={() => setSelectedId(hit.id)}
              aria-label={`Preview ${hit.title}`}
              aria-pressed={hit.id === selectedId}
            >
              {hit.id !== null ? (
                <img
                  src={getGetMediaContentUrl(hit.id)}
                  alt=""
                  loading="lazy"
                  decoding="async"
                />
              ) : (
                <span className="pi-contact-sheet__missing" aria-hidden="true">
                  <Icon name="ring" size={16} />
                </span>
              )}
              <span className="pi-contact-sheet__caption">{truncate(hit.title, 60)}</span>
            </button>
            <span className="pi-contact-sheet__dims">
              {hit.width !== null && hit.height !== null
                ? `${hit.width}×${hit.height}`
                : "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** `search_media`: a contact sheet with a local lightbox preview. */
export function SearchMediaPanel({ item }: PanelProps) {
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Looking through the contact sheet." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="ring"
        title="The media search did not return"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }
  const data = item.data;
  return (
    <div className="pi-media-panel">
      <header className="pi-media-panel__head">
        <div>
          <p className="eyebrow">Contact sheet</p>
          <strong>{textField(data, "query") ?? "Media search"}</strong>
        </div>
        <span>{formatNumber(hitsOf(data).length)} specimens</span>
      </header>
      <ContactSheet hits={hitsOf(data)} />
    </div>
  );
}

function SpecimenSection({
  label,
  text,
  pre = false,
}: {
  readonly label: string;
  readonly text: string;
  readonly pre?: boolean;
}) {
  return (
    <section className="pi-specimen__section">
      <p className="eyebrow">{label}</p>
      {pre ? <pre>{text}</pre> : <p>{text}</p>}
    </section>
  );
}

/** `get_media`: a specimen sheet with caption, OCR, tags, and the image. */
export function GetMediaPanel({ item }: PanelProps) {
  const data = item.data;
  const mediaId =
    recordId(data, "media_id") ??
    recordId(item.arguments, "media_id") ??
    (item.resource?.resourceType === "media" ? item.resource.resourceId : null);
  const query = useGetMedia(mediaId ?? 0, {
    query: { enabled: mediaId !== null, retry: false },
  });

  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Mounting the image and its reading notes." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="ring"
        title="The specimen could not be read"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }
  if (mediaId === null) {
    return (
      <PanelEmpty
        icon="ring"
        title="No media id in this result"
        detail="The inspector received no specimen to mount."
      />
    );
  }

  const media = query.data;
  const title =
    textField(data, "title") ??
    media?.title ??
    textField(data, "file_name") ??
    media?.file_name ??
    `media:${mediaId}`;
  const caption = textField(data, "caption") ?? media?.caption ?? "";
  const summary = textField(data, "summary") ?? media?.summary ?? "";
  const ocr = textField(data, "ocr_text") ?? media?.ocr_text ?? "";
  const tags = stringList(data?.tags).length > 0 ? stringList(data?.tags) : (media?.tags ?? []);
  const href = safeResourceUrl(data?.viewer_url, {
    type: "media",
    id: mediaId,
    chunk: null,
    title,
  });

  return (
    <div className="pi-specimen">
      <header className="pi-specimen__head">
        <p className="eyebrow">Specimen sheet</p>
        <strong>{title}</strong>
        {href ? <Link to={href}>Open in viewer</Link> : null}
      </header>
      <div className="pi-specimen__plate">
        <InspectorMediaStage mediaId={mediaId} compact />
      </div>
      <div className="pi-specimen__notes">
        {caption.length > 0 ? <SpecimenSection label="Caption" text={caption} /> : null}
        {summary.length > 0 ? <SpecimenSection label="Summary" text={summary} /> : null}
        {ocr.length > 0 ? <SpecimenSection label="OCR text" text={ocr} pre /> : null}
        {tags.length > 0 ? (
          <section className="pi-specimen__section">
            <p className="eyebrow">Tags</p>
            <div className="pi-specimen__tags">
              {tags.map((tag) => (
                <span key={tag}>#{tag}</span>
              ))}
            </div>
          </section>
        ) : null}
        {caption.length === 0 && summary.length === 0 && ocr.length === 0 ? (
          <PanelEmpty
            icon="ring"
            title="No reading notes"
            detail="The image is mounted, but no caption, summary, or OCR text was recorded."
          />
        ) : null}
      </div>
    </div>
  );
}
