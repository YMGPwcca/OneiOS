# OneiOS documentation

**Galaxy S26 Ultra · SM-S948B / m3q / SM8850 · iOS 27.0.1 · experimental**

[← Project home](../README.md) · [Current evidence](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md) · [Companion OneOS](https://github.com/YMGPwcca/OneOS/tree/feat/sm8850-reboot-smoke/docs)

> [!CAUTION]
> **Booted is not accepted.** A physical full-run reached guest-ready and first frame for ~600.6 s with KGSL acceleration. The device was very hot and visibly laggy. Unassisted recovery, independent watchdog qualification and a separate thermal guard are not yet proven. Normal OneOS app switching is blocked for SM8850.

## Find what you need

| Question | Start here |
| :--- | :--- |
| What works on the S26 Ultra today? | [Physical status & proof](SM8850_LIVE_STATUS_2026-11-20.md) |
| What do we fix next? | [Safety-first roadmap](TODO.md) |
| How does this system work? | [Architecture](architecture.md) |
| How do I build and test without touching the phone? | [CachyOS local build](building.md) |
| Why did the phone lag and heat up? | [Interactive performance triage](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) |
| How did reboot/takeover behave? | [Framework timeline](SM8850_FRAMEWORK_TAKEOVER.md) |

---

#
#
 
0
1
 
·
 
S
t
a
r
t
 
h
e
r
e




|
 
D
o
c
u
m
e
n
t
 
|
 
W
h
a
t
 
t
o
 
u
s
e
 
i
t
 
f
o
r
 
|


|
 
:
-
-
-
 
|
 
:
-
-
-
 
|


|
 
[
S
M
8
8
5
0
 
L
I
V
E
 
S
T
A
T
U
S
 
2
0
2
6
-
1
1
-
2
0
]
(
S
M
8
8
5
0
_
L
I
V
E
_
S
T
A
T
U
S
_
2
0
2
6
-
1
1
-
2
0
.
m
d
)
 
|
 
C
u
r
r
e
n
t
 
v
e
r
i
f
i
e
d
 
s
t
a
t
e
 
·
 
p
h
y
s
i
c
a
l
 
r
u
n
,
 
l
i
m
i
t
a
t
i
o
n
s
 
a
n
d
 
e
v
i
d
e
n
c
e
 
|


|
 
[
T
O
D
O
]
(
T
O
D
O
.
m
d
)
 
|
 
E
n
g
i
n
e
e
r
i
n
g
 
q
u
e
u
e
 
·
 
P
0
 
s
a
f
e
t
y
 
t
h
r
o
u
g
h
 
P
3
 
a
c
c
e
p
t
a
n
c
e
 
|


|
 
[
a
r
c
h
i
t
e
c
t
u
r
e
]
(
a
r
c
h
i
t
e
c
t
u
r
e
.
m
d
)
 
|
 
H
o
w
 
h
o
s
t
e
d
 
X
N
U
,
 
i
O
S
 
t
a
s
k
s
 
a
n
d
 
A
n
d
r
o
i
d
 
h
a
r
d
w
a
r
e
 
i
n
t
e
g
r
a
t
e
 
|


|
 
[
b
u
i
l
d
i
n
g
]
(
b
u
i
l
d
i
n
g
.
m
d
)
 
|
 
B
u
i
l
d
,
 
t
e
s
t
,
 
v
e
r
i
f
y
 
a
n
d
 
p
a
c
k
a
g
e
 
l
o
c
a
l
l
y
 
o
n
 
C
a
c
h
y
O
S
 
|


|
 
[
S
M
8
8
5
0
 
F
U
L
L
 
I
O
S
 
1
0
M
I
N
]
(
S
M
8
8
5
0
_
F
U
L
L
_
I
O
S
_
1
0
M
I
N
.
m
d
)
 
|
 
F
u
l
l
 
F
r
a
m
e
w
o
r
k
 
t
a
k
e
o
v
e
r
 
r
e
c
o
r
d
 
a
n
d
 
o
n
e
-
s
h
o
t
 
s
t
a
g
i
n
g
 
—
 
*
*
h
i
s
t
o
r
i
c
a
l
;
 
n
o
t
 
a
 
r
e
t
e
s
t
 
i
n
s
t
r
u
c
t
i
o
n
*
*
 
|




#
#
 
0
2
 
·
 
D
e
v
i
c
e
,
 
s
a
f
e
t
y
 
&
 
r
e
c
o
v
e
r
y




|
 
D
o
c
u
m
e
n
t
 
|
 
W
h
a
t
 
t
o
 
u
s
e
 
i
t
 
f
o
r
 
|


|
 
:
-
-
-
 
|
 
:
-
-
-
 
|


|
 
[
S
M
8
8
5
0
 
P
O
R
T
]
(
S
M
8
8
5
0
_
P
O
R
T
.
m
d
)
 
|
 
S
M
8
8
5
0
 
h
a
r
d
w
a
r
e
 
f
a
c
t
s
 
a
n
d
 
a
c
c
e
p
t
a
n
c
e
 
b
o
u
n
d
a
r
i
e
s
 
|


|
 
[
S
M
8
8
5
0
 
F
R
A
M
E
W
O
R
K
 
T
A
K
E
O
V
E
R
]
(
S
M
8
8
5
0
_
F
R
A
M
E
W
O
R
K
_
T
A
K
E
O
V
E
R
.
m
d
)
 
|
 
E
x
e
c
u
t
e
d
 
t
a
k
e
o
v
e
r
 
t
i
m
e
l
i
n
e
 
a
n
d
 
c
u
r
r
e
n
t
 
b
l
o
c
k
e
r
s
 
|


|
 
[
S
M
8
8
5
0
 
R
E
B
O
O
T
 
S
M
O
K
E
]
(
S
M
8
8
5
0
_
R
E
B
O
O
T
_
S
M
O
K
E
.
m
d
)
 
|
 
R
e
b
o
o
t
-
o
n
l
y
 
s
m
o
k
e
 
a
n
d
 
o
b
s
e
r
v
e
d
 
r
e
t
u
r
n
 
r
e
c
e
i
p
t
s
 
|


|
 
[
S
M
8
8
5
0
 
W
A
T
C
H
D
O
G
 
A
C
C
E
P
T
A
N
C
E
]
(
S
M
8
8
5
0
_
W
A
T
C
H
D
O
G
_
A
C
C
E
P
T
A
N
C
E
.
m
d
)
 
|
 
W
a
t
c
h
d
o
g
 
p
r
o
v
e
n
a
n
c
e
 
a
n
d
 
m
i
s
s
i
n
g
 
i
n
d
e
p
e
n
d
e
n
t
 
q
u
a
l
i
f
i
c
a
t
i
o
n
 
|


|
 
[
S
M
8
8
5
0
 
W
A
T
C
H
D
O
G
 
S
U
P
E
R
V
I
S
O
R
]
(
S
M
8
8
5
0
_
W
A
T
C
H
D
O
G
_
S
U
P
E
R
V
I
S
O
R
.
m
d
)
 
|
 
W
a
t
c
h
d
o
g
 
s
u
p
e
r
v
i
s
o
r
 
d
e
s
i
g
n
 
a
n
d
 
h
e
a
r
t
b
e
a
t
 
s
e
m
a
n
t
i
c
s
 
|


|
 
[
S
M
8
8
5
0
 
T
A
K
E
O
V
E
R
 
R
E
T
U
R
N
 
G
A
T
E
0
]
(
S
M
8
8
5
0
_
T
A
K
E
O
V
E
R
_
R
E
T
U
R
N
_
G
A
T
E
0
.
m
d
)
 
|
 
O
r
i
g
i
n
a
l
 
r
e
a
d
-
o
n
l
y
 
g
a
t
e
,
 
n
o
w
 
a
 
h
i
s
t
o
r
i
c
a
l
 
d
e
c
i
s
i
o
n
 
m
e
m
o
 
|


|
 
[
S
M
8
8
5
0
 
R
E
C
O
V
E
R
Y
 
D
R
Y
 
R
U
N
]
(
S
M
8
8
5
0
_
R
E
C
O
V
E
R
Y
_
D
R
Y
_
R
U
N
.
m
d
)
 
|
 
N
o
n
-
d
i
s
r
u
p
t
i
v
e
 
r
e
c
o
v
e
r
y
 
a
u
d
i
t
 
a
n
d
 
p
h
y
s
i
c
a
l
 
i
n
p
u
t
 
e
v
i
d
e
n
c
e
 
|


|
 
[
S
M
8
8
5
0
 
O
R
I
G
I
N
A
L
 
A
U
D
I
T
]
(
S
M
8
8
5
0
_
O
R
I
G
I
N
A
L
_
A
U
D
I
T
.
m
d
)
 
|
 
D
e
t
a
i
l
e
d
 
p
a
s
s
i
v
e
 
d
e
v
i
c
e
/
s
a
f
e
t
y
 
a
u
d
i
t
 
(
h
i
s
t
o
r
i
c
a
l
 
e
v
i
d
e
n
c
e
)
 
|




#
#
 
0
3
 
·
 
i
O
S
 
g
r
a
p
h
i
c
s
,
 
t
o
u
c
h
 
&
 
p
e
r
f
o
r
m
a
n
c
e




|
 
D
o
c
u
m
e
n
t
 
|
 
W
h
a
t
 
t
o
 
u
s
e
 
i
t
 
f
o
r
 
|


|
 
:
-
-
-
 
|
 
:
-
-
-
 
|


|
 
[
S
M
8
8
5
0
 
I
O
S
 
I
N
T
E
R
A
C
T
I
V
E
 
P
E
R
F
 
T
R
I
A
G
E
]
(
S
M
8
8
5
0
_
I
O
S
_
I
N
T
E
R
A
C
T
I
V
E
_
P
E
R
F
_
T
R
I
A
G
E
.
m
d
)
 
|
 
C
P
U
/
G
P
U
 
l
a
g
 
a
n
a
l
y
s
i
s
,
 
A
/
B
 
r
e
s
u
l
t
s
 
a
n
d
 
h
y
p
o
t
h
e
s
e
s
 
|


|
 
[
S
M
8
8
5
0
 
I
O
S
 
I
N
T
E
R
A
C
T
I
V
E
 
P
E
R
F
 
C
A
P
T
U
R
E
]
(
S
M
8
8
5
0
_
I
O
S
_
I
N
T
E
R
A
C
T
I
V
E
_
P
E
R
F
_
C
A
P
T
U
R
E
.
m
d
)
 
|
 
C
a
p
t
u
r
e
 
f
o
r
m
a
t
 
a
n
d
 
m
a
t
c
h
e
d
 
t
o
u
c
h
/
U
I
 
b
e
n
c
h
m
a
r
k
 
m
e
t
h
o
d
 
|


|
 
[
S
M
8
8
5
0
 
I
O
S
 
T
O
U
C
H
 
P
R
E
V
I
E
W
]
(
S
M
8
8
5
0
_
I
O
S
_
T
O
U
C
H
_
P
R
E
V
I
E
W
.
m
d
)
 
|
 
B
o
u
n
d
e
d
 
n
o
n
-
t
a
k
e
o
v
e
r
 
t
o
u
c
h
 
p
r
e
v
i
e
w
 
|


|
 
[
S
M
8
8
5
0
 
I
O
S
 
G
P
U
 
V
I
S
U
A
L
]
(
S
M
8
8
5
0
_
I
O
S
_
G
P
U
_
V
I
S
U
A
L
.
m
d
)
 
|
 
P
h
y
s
i
c
a
l
 
v
i
s
u
a
l
 
G
P
U
 
t
r
i
a
l
 
a
n
d
 
c
r
i
t
e
r
i
a
 
|


|
 
[
S
M
8
8
5
0
 
I
O
S
 
G
P
U
 
B
E
N
C
H
]
(
S
M
8
8
5
0
_
I
O
S
_
G
P
U
_
B
E
N
C
H
.
m
d
)
 
|
 
B
o
u
n
d
e
d
 
G
P
U
-
a
u
t
o
 
b
e
n
c
h
 
w
i
t
h
o
u
t
 
F
r
a
m
e
w
o
r
k
 
s
t
o
p
 
|


|
 
[
S
M
8
8
5
0
 
I
O
S
 
G
P
U
 
B
E
N
C
H
 
R
E
T
R
Y
]
(
S
M
8
8
5
0
_
I
O
S
_
G
P
U
_
B
E
N
C
H
_
R
E
T
R
Y
.
m
d
)
 
|
 
E
a
r
l
i
e
r
 
p
r
e
f
l
i
g
h
t
 
f
a
i
l
u
r
e
 
a
n
d
 
f
o
l
l
o
w
-
u
p
 
|


|
 
[
S
M
8
8
5
0
 
G
P
U
 
H
A
R
D
W
A
R
E
 
A
C
C
E
P
T
A
N
C
E
]
(
S
M
8
8
5
0
_
G
P
U
_
H
A
R
D
W
A
R
E
_
A
C
C
E
P
T
A
N
C
E
.
m
d
)
 
|
 
K
G
S
L
/
A
d
r
e
n
o
 
h
a
r
d
w
a
r
e
 
e
v
i
d
e
n
c
e
 
|


|
 
[
S
M
8
8
5
0
 
G
P
U
 
D
A
T
A
 
S
N
A
P
S
H
O
T
]
(
S
M
8
8
5
0
_
G
P
U
_
D
A
T
A
_
S
N
A
P
S
H
O
T
.
m
d
)
 
|
 
I
s
o
l
a
t
e
d
 
A
P
F
S
 
D
a
t
a
 
c
l
o
n
e
 
p
r
o
t
o
c
o
l
 
|


|
 
[
S
M
8
8
5
0
 
G
U
I
 
C
R
A
S
H
]
(
S
M
8
8
5
0
_
G
U
I
_
C
R
A
S
H
.
m
d
)
 
|
 
G
u
e
s
t
 
G
U
I
 
c
r
a
s
h
 
i
n
v
e
s
t
i
g
a
t
i
o
n
 
|




#
#
 
0
4
 
·
 
B
u
i
l
d
,
 
i
m
a
g
e
 
&
 
r
u
n
t
i
m
e
 
r
e
f
e
r
e
n
c
e




|
 
D
o
c
u
m
e
n
t
 
|
 
W
h
a
t
 
t
o
 
u
s
e
 
i
t
 
f
o
r
 
|


|
 
:
-
-
-
 
|
 
:
-
-
-
 
|


|
 
[
b
o
o
t
e
r
]
(
b
o
o
t
e
r
.
m
d
)
 
|
 
x
n
u
h
o
s
t
 
i
n
t
e
r
n
a
l
s
,
 
h
o
s
t
c
a
l
l
s
,
 
m
e
m
o
r
y
 
a
n
d
 
v
C
P
U
s
 
|


|
 
[
g
p
u
]
(
g
p
u
.
m
d
)
 
|
 
v
i
r
t
i
o
-
g
p
u
,
 
d
r
m
2
k
g
s
l
,
 
n
a
t
i
v
e
 
A
d
r
e
n
o
 
p
a
t
h
 
a
n
d
 
p
o
l
i
c
i
e
s
 
|


|
 
[
h
a
r
d
w
a
r
e
]
(
h
a
r
d
w
a
r
e
.
m
d
)
 
|
 
D
e
v
i
c
e
 
b
r
i
d
g
e
s
,
 
b
a
c
k
e
n
d
 
s
e
l
e
c
t
o
r
s
 
a
n
d
 
h
a
r
d
w
a
r
e
 
i
n
v
e
n
t
o
r
y
 
|


|
 
[
u
s
e
r
l
a
n
d
]
(
u
s
e
r
l
a
n
d
.
m
d
)
 
|
 
i
O
S
 
2
7
 
u
s
e
r
l
a
n
d
,
 
c
a
c
h
e
s
,
 
s
i
g
n
i
n
g
 
a
n
d
 
t
h
e
 
M
e
t
a
l
 
b
u
n
d
l
e
 
|


|
 
[
i
m
a
g
e
-
f
o
r
m
a
t
]
(
i
m
a
g
e
-
f
o
r
m
a
t
.
m
d
)
 
|
 
M
a
n
i
f
e
s
t
,
 
A
P
F
S
 
i
m
a
g
e
s
,
 
h
a
s
h
e
s
 
a
n
d
 
t
r
u
s
t
e
d
 
D
a
t
a
 
s
e
e
d
 
|


|
 
[
r
e
l
e
a
s
e
s
]
(
r
e
l
e
a
s
e
s
.
m
d
)
 
|
 
A
r
t
i
f
a
c
t
 
f
o
r
m
a
t
 
a
n
d
 
r
e
l
e
a
s
e
 
v
e
r
i
f
i
c
a
t
i
o
n
 
|


|
 
[
S
M
8
8
5
0
 
I
M
A
G
E
 
R
E
A
D
I
N
E
S
S
]
(
S
M
8
8
5
0
_
I
M
A
G
E
_
R
E
A
D
I
N
E
S
S
.
m
d
)
 
|
 
I
m
a
g
e
 
p
r
o
v
e
n
a
n
c
e
 
a
n
d
 
s
t
a
g
e
d
 
t
r
u
s
t
 
c
h
e
c
k
s
 
|


|
 
[
S
M
8
8
5
0
 
N
O
 
C
O
P
Y
 
I
M
A
G
E
 
A
D
A
P
T
E
R
]
(
S
M
8
8
5
0
_
N
O
_
C
O
P
Y
_
I
M
A
G
E
_
A
D
A
P
T
E
R
.
m
d
)
 
|
 
I
m
a
g
e
 
s
t
a
g
i
n
g
 
d
e
s
i
g
n
 
e
x
p
l
o
r
a
t
i
o
n
 
|


|
 
[
r
e
f
e
r
e
n
c
e
s
]
(
r
e
f
e
r
e
n
c
e
s
.
m
d
)
 
|
 
S
o
u
r
c
e
 
p
r
o
v
e
n
a
n
c
e
 
a
n
d
 
r
e
s
e
a
r
c
h
 
l
i
n
k
s
 
|




#
#
 
0
5
 
·
 
P
r
o
j
e
c
t
 
w
o
r
k
f
l
o
w
 
&
 
h
i
s
t
o
r
i
c
a
l
 
d
e
c
i
s
i
o
n
s




|
 
D
o
c
u
m
e
n
t
 
|
 
W
h
a
t
 
t
o
 
u
s
e
 
i
t
 
f
o
r
 
|


|
 
:
-
-
-
 
|
 
:
-
-
-
 
|


|
 
[
a
g
e
n
t
s
]
(
a
g
e
n
t
s
.
m
d
)
 
|
 
C
o
n
t
r
i
b
u
t
i
o
n
 
r
u
l
e
s
,
 
e
v
i
d
e
n
c
e
 
h
a
n
d
l
i
n
g
 
a
n
d
 
l
o
c
a
l
-
f
i
r
s
t
 
c
h
e
c
k
s
 
|


|
 
[
p
l
a
n
]
(
p
l
a
n
.
m
d
)
 
|
 
C
u
r
r
e
n
t
 
S
2
6
 
U
l
t
r
a
 
e
n
g
i
n
e
e
r
i
n
g
 
p
l
a
n
 
|


|
 
[
n
e
w
t
o
d
o
]
(
n
e
w
t
o
d
o
.
m
d
)
 
|
 
R
e
d
i
r
e
c
t
 
f
o
r
 
t
h
e
 
f
o
r
m
e
r
 
p
a
u
s
e
 
l
o
g
 
a
n
d
 
s
u
p
e
r
s
e
d
e
d
 
w
o
r
k
 
q
u
e
u
e
s
 
|


|
 
[
S
T
Y
L
E
 
G
U
I
D
E
]
(
S
T
Y
L
E
_
G
U
I
D
E
.
m
d
)
 
|
 
L
a
y
o
u
t
,
 
s
t
a
t
u
s
 
v
o
c
a
b
u
l
a
r
y
 
a
n
d
 
l
i
n
k
 
c
o
n
v
e
n
t
i
o
n
s
 
|

---

## Reading the evidence

- **OBSERVED** — directly supported by device output or an archived run; never an automatic acceptance of related behavior.
- **PASS** — a named test, with stated device/fixture scope, met its exact criterion.
- **NOT VERIFIED** — missing evidence; do not silently convert it to failure or success.
- **BLOCKED** — a safety or technical precondition prevents the next action.
- **HISTORICAL** — accurate for an earlier point in the project, not a current recommendation.

> [!NOTE]
> These files intentionally retain older diagnostic evidence where it is useful, but the **current device and decision scope is the Galaxy S26 Ultra**. Current results always take precedence over outdated pretrial plans. See [documentation style](STYLE_GUIDE.md).

Last documentation review: **2026-11-20**. Device and firmware are intentionally pinned; do not generalize the results to a different build.
