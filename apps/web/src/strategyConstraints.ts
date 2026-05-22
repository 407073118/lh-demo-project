import type { StrategyConstraint, StrategyParams } from "./api";

export function evaluateStrategyConstraints(
  params: StrategyParams,
  constraints: StrategyConstraint[]
): string | null {
  for (const constraint of constraints) {
    if (constraint.type === "lt") {
      const left = params[constraint.left];
      const right = params[constraint.right];
      if (typeof left !== "number" || typeof right !== "number") {
        return constraint.message;
      }
      if (!Number.isFinite(left) || !Number.isFinite(right) || !(left < right)) {
        return constraint.message;
      }
    }

    if (constraint.type === "ordered") {
      const values = constraint.fields.map((field) => params[field]);
      if (values.some((value) => typeof value !== "number")) {
        return constraint.message;
      }
      const numericValues = values as number[];
      if (numericValues.some((value) => !Number.isFinite(value))) {
        return constraint.message;
      }
      for (let index = 0; index < numericValues.length - 1; index += 1) {
        if (!(numericValues[index] < numericValues[index + 1])) {
          return constraint.message;
        }
      }
      if (constraint.min != null && !(numericValues[0] > constraint.min)) {
        return constraint.message;
      }
      if (constraint.max != null && !(numericValues[numericValues.length - 1] < constraint.max)) {
        return constraint.message;
      }
    }
  }
  return null;
}
