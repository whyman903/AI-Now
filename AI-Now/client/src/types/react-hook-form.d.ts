declare module "react-hook-form" {
  import * as React from "react";

  export type FieldValues = Record<string, unknown>;
  export type FieldPath<TFieldValues extends FieldValues = FieldValues> =
    keyof TFieldValues extends string
      ? keyof TFieldValues | (string & {})
      : string;

  export interface ControllerFieldState {
    error?: { message?: string } | undefined;
    invalid?: boolean;
    isTouched?: boolean;
  }

  export interface ControllerRenderProps<
    TFieldValues extends FieldValues = FieldValues
  > {
    field: {
      onChange: (...event: any[]) => void;
      onBlur: () => void;
      value: any;
      ref: React.Ref<any>;
      name: FieldPath<TFieldValues>;
    };
    fieldState: ControllerFieldState;
    formState: any;
  }

  export interface ControllerProps<
    TFieldValues extends FieldValues = FieldValues,
    TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
    TContext = any
  > {
    name: TName;
    control: any;
    defaultValue?: any;
    rules?: Record<string, unknown>;
    shouldUnregister?: boolean;
    render: (props: ControllerRenderProps<TFieldValues>) => React.ReactNode;
  }

  export const Controller: React.FC<ControllerProps<any, any>>;

  export interface FormProviderProps<
    TFieldValues extends FieldValues = FieldValues,
    TContext = any
  > {
    children: React.ReactNode;
    value: any;
  }

  export const FormProvider: React.FC<FormProviderProps>;

  export function useFormContext<
    TFieldValues extends FieldValues = FieldValues
  >(): {
    getFieldState: (
      name: FieldPath<TFieldValues>,
      formState?: any
    ) => ControllerFieldState;
    formState: any;
  };
}
