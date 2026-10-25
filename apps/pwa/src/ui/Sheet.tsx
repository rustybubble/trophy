import { useEffect, type ReactNode } from "react";
import { CloseIcon } from "./icons.tsx";

/** A bottom sheet: tap the backdrop, the × or press Escape to close. */
export function Sheet(props: { title: ReactNode; onClose: () => void; tall?: boolean; children: ReactNode }) {
  const { onClose } = props;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="sheet-wrap" onClick={onClose}>
      <section
        className={props.tall ? "sheet tall" : "sheet"}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sheet-head">
          <h2>{props.title}</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            <CloseIcon />
          </button>
        </header>
        <div className="sheet-body">{props.children}</div>
      </section>
    </div>
  );
}
