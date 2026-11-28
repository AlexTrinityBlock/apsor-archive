import { useEffect, useState, useSyncExternalStore } from "react";

import type { CompanionAction } from "../actions";
import type { CompanionStreamInput } from "../director";
import { CompanionDirectorEngine } from "../director-engine";

export interface CompanionDirectorInput {
  readonly stream: CompanionStreamInput | null;
  readonly draft: string;
  readonly conversationKey: string;
  readonly held: boolean;
}

export interface CompanionDirector {
  readonly action: CompanionAction;
  readonly poke: () => void;
}

/** Feed chat observations into the clocked director and read its pose. */
export function useCompanionDirector(input: CompanionDirectorInput): CompanionDirector {
  const [engine] = useState(() => new CompanionDirectorEngine());

  useEffect(() => () => engine.dispose(), [engine]);

  useEffect(() => {
    engine.noteConversation(input.conversationKey);
  }, [engine, input.conversationKey]);

  useEffect(() => {
    engine.noteDraft(input.draft);
  }, [engine, input.draft]);

  useEffect(() => {
    engine.noteStream(input.stream);
  }, [engine, input.stream]);

  useEffect(() => {
    engine.setHeld(input.held);
  }, [engine, input.held]);

  const action = useSyncExternalStore(engine.subscribe, engine.getSnapshot);
  return { action, poke: () => engine.poke() };
}
