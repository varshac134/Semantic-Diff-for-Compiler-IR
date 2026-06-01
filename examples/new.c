#include <stdio.h>

static inline int add_one_inline(int x) {
    return x + 1;
}

int main(void) {
    int value = 42;
    int result = add_one_inline(value);
    printf("result=%d\n", result);
    return 0;
}
