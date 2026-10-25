import { useRef, useState } from "react";
import { TransformComponent, TransformWrapper, type ReactZoomPanPinchContentRef } from "react-zoom-pan-pinch";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface ImageViewProps {
  readonly src: string;
  readonly alt: string;
  readonly downloadUrl?: string;
  readonly downloadName?: string;
}

/**
 * Native image rendering with wheel/pinch zoom, pan, fit reset, and a true
 * 1:1 control based on the image's natural width.
 */
export function ImageView({ src, alt, downloadUrl, downloadName }: ImageViewProps) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  const [naturalScale, setNaturalScale] = useState(1);
  const imageRef = useRef<HTMLImageElement>(null);
  const controlsRef = useRef<ReactZoomPanPinchContentRef | null>(null);

  const showActualSize = () => {
    controlsRef.current?.centerView(Math.max(0.05, naturalScale), 180);
  };

  if (failed) {
    return (
      <div className="viewer-state viewer-state--error" role="alert">
        <span className="viewer-state__mark" aria-hidden="true">
          <Icon name="info" size={22} />
        </span>
        <p className="eyebrow">{t("library.viewer.image.unavailableEyebrow")}</p>
        <h2>{t("library.viewer.image.unavailableTitle")}</h2>
        <p>{t("library.viewer.image.unavailableDescription")}</p>
        {downloadUrl ? (
          <a className="btn btn--ghost btn--sm" href={downloadUrl} download={downloadName}>
            <Icon name="arrow-down" size={15} />
            {t("library.viewer.downloadOriginal")}
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <TransformWrapper
      ref={controlsRef}
      initialScale={1}
      minScale={0.2}
      maxScale={8}
      centerOnInit
      limitToBounds={false}
      doubleClick={{ mode: "zoomIn", step: 0.7 }}
      wheel={{ step: 0.12 }}
      panning={{ velocityDisabled: true }}
    >
      {({ zoomIn, zoomOut, resetTransform }) => (
        <div className="viewer-image">
          <div className="viewer-image__bar">
            <span className="viewer-image__hint">
              {t("library.viewer.image.hint")}
            </span>
            <div className="viewer-image__controls">
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                onClick={() => zoomOut(0.2)}
                aria-label={t("library.viewer.zoomOut")}
                title={t("library.viewer.zoomOut")}
              >
                <span aria-hidden="true">−</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                onClick={() => zoomIn(0.2)}
                aria-label={t("library.viewer.zoomIn")}
                title={t("library.viewer.zoomIn")}
              >
                <span aria-hidden="true">+</span>
              </Button>
              <Button variant="ghost" size="sm" onClick={() => resetTransform(180)}>
                {t("library.viewer.image.fit")}
              </Button>
              <Button variant="ghost" size="sm" onClick={showActualSize}>
                1:1
              </Button>
            </div>
          </div>
          <TransformComponent
            wrapperClass="viewer-image__stage"
            contentClass="viewer-image__content"
            wrapperStyle={{ width: "100%", height: "100%" }}
            contentStyle={{
              width: "100%",
              height: "100%",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <img
              ref={imageRef}
              src={src}
              alt={alt}
              className="viewer-image__img"
              decoding="async"
              draggable={false}
              onLoad={() => {
                const image = imageRef.current;
                if (!image || image.clientWidth === 0) {
                  return;
                }
                setNaturalScale(image.naturalWidth / image.clientWidth);
              }}
              onError={() => setFailed(true)}
            />
          </TransformComponent>
        </div>
      )}
    </TransformWrapper>
  );
}
