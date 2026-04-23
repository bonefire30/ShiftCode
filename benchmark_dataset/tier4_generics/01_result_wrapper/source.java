import java.util.*;
import java.util.stream.Collectors;

/**
 * Tier4 generics: Result success/failure wrapper and filterNonNull over a list.
 * Migration target: Go 1.18+ generics (struct + type parameters + FilterNonNull on pointers).
 */
public class ResultWrapper {

    public static class Result<T, E> {
        private final boolean success;
        private final T value;
        private final E error;

        private Result(boolean success, T value, E error) {
            this.success = success;
            this.value = value;
            this.error = error;
        }

        public static <T, E> Result<T, E> success(T value) {
            return new Result<>(true, value, null);
        }

        public static <T, E> Result<T, E> failure(E error) {
            return new Result<>(false, null, error);
        }

        public boolean isSuccess() {
            return success;
        }

        public T getValue() {
            return value;
        }

        public E getError() {
            return error;
        }
    }

    public static <T> List<T> filterNonNull(List<T> items) {
        if (items == null) {
            return new ArrayList<>();
        }
        return items.stream().filter(Objects::nonNull).collect(Collectors.toList());
    }
}
