import type { ButtonHTMLAttributes, ComponentProps, ReactNode } from "react";
import { Link } from "react-router-dom";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "ink" | "paper";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonStyleOptions {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly block?: boolean;
  readonly iconOnly?: boolean;
  readonly className?: string;
}

/** Builds the shared button class list for buttons and router links. */
export function buttonClassName({
  variant = "secondary",
  size = "md",
  block = false,
  iconOnly = false,
  className,
}: ButtonStyleOptions): string {
  return [
    "btn",
    `btn--${variant}`,
    `btn--${size}`,
    block ? "btn--block" : null,
    iconOnly ? "btn--icon" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
}

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className">,
    ButtonStyleOptions {
  readonly children: ReactNode;
}

/** The archive's primary action control. */
export function Button({
  variant = "secondary",
  size = "md",
  block = false,
  iconOnly = false,
  className,
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClassName({ variant, size, block, iconOnly, className })}
      {...rest}
    >
      {children}
    </button>
  );
}

type RouterLinkProps = ComponentProps<typeof Link>;

export interface ButtonLinkProps
  extends Omit<RouterLinkProps, "className">,
    ButtonStyleOptions {
  readonly children: ReactNode;
}

/** A router link that wears the same visual treatment as Button. */
export function ButtonLink({
  variant = "secondary",
  size = "md",
  block = false,
  iconOnly = false,
  className,
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link
      className={buttonClassName({ variant, size, block, iconOnly, className })}
      {...rest}
    >
      {children}
    </Link>
  );
}
