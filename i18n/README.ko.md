<p align="center">
  <img src="https://img.shields.io/badge/ClaudeKit-v2.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">ClaudeKit</h1>

<p align="center">
  <strong><a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>를 위한 프로덕션 수준의 멀티 에이전트 오케스트레이션 시스템.</strong><br>
  구조화된 계획. 리뷰 게이트. 안전한 실행. 품질 검증. 모든 언어 지원.
</p>

<p align="center">
  <a href="#빠른-시작">빠른 시작</a> &middot;
  <a href="#작동-방식">작동 방식</a> &middot;
  <a href="#명령어">명령어</a> &middot;
  <a href="#에이전트">에이전트</a> &middot;
  <a href="#기여하기">기여하기</a>
</p>

---

### 언어 선택 | Select Language

[English](../README.md) | [العربية](README.ar.md) | [中文](README.zh.md) | [Espanol](README.es.md) | [Francais](README.fr.md) | [日本語](README.ja.md) | **한국어**

---

## 왜 ClaudeKit인가?

Claude Code는 그 자체로 강력합니다. ClaudeKit은 이를 **구조화되고, 안전하며, 감사 가능**하게 만듭니다.

ClaudeKit 없이는 AI 어시스턴트가 직접 변경을 수행합니다 -- 계획 없이, 리뷰 없이, 롤백 없이. ClaudeKit과 함께라면 모든 변경이 파이프라인을 따릅니다: 계획하고, 리뷰하고, 안전하게 실행하고, 결과를 검증합니다.

### 핵심 구성 요소

| 구성 요소 | 수량 | 설명 |
|----------|------|------|
| 에이전트 | 13 | 각 작업에 특화된 에이전트 |
| 명령어 | 20+ | 바로 사용 가능한 명령어 |
| 스킬 | 55+ | 재사용 가능한 스킬 |
| 모드 | 7 | 다양한 동작 모드 |
| 안전 가드 | 29 | 모든 설정을 검증하는 가드 |
| 언어 템플릿 | 11 | Python, TypeScript, Java, Go 등 지원 |
| MCP 서버 | 5 | 모델 컨텍스트 프로토콜 통합 |

---

## 빠른 시작

### 설치

```bash
git clone https://github.com/omarmokhtar/claudekit.git
./claudekit/install.sh /path/to/your-project --full
```

설치 프로그램이 프로젝트 언어를 자동 감지하고, `.claude/` 디렉토리를 프로젝트에 복사하고, `CLAUDE.md`와 `CONSTITUTION.md`를 생성하고, 빌드/테스트/린트 명령어로 훅을 설정합니다.

### 설치 옵션

```bash
# 전체 설치 (에이전트 + 명령어 + 스킬 + 훅 + 오퍼레이션)
./install.sh ./my-project --full

# 최소 설치 (에이전트 + 명령어 + 오퍼레이션만)
./install.sh ./my-project --minimal

# 언어 사전 설정
./install.sh ./my-project --full --language typescript

# 기존 설치 덮어쓰기
./install.sh ./my-project --full --force
```

### 사용법

Claude Code에서 프로젝트를 열고 실행하세요:

```
/plan JWT 토큰을 사용한 사용자 인증 추가
```

ClaudeKit이 인수합니다 -- 플래너가 코드베이스를 탐색하고 ops.json 설정과 함께 계획을 작성하고, 리뷰어가 검증하고, 구현자가 자동 백업과 함께 실행하고, 검증자가 결과를 확인합니다.

---

## 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/plan` | ops.json과 함께 구현 계획 생성 | `/plan API에 속도 제한 추가` |
| `/review` | 계획 검증 (임계값 90/100) | `/review` |
| `/implement` | 승인된 계획 실행 | `/implement` |
| `/verify` | 품질 검사 실행 (임계값 80/100) | `/verify` |
| `/debug` | 버그 진단 (읽기 전용) | `/debug 로그인이 왜 500을 반환하나요?` |
| `/docs` | 문서 생성 | `/docs 인증 모듈 API 레퍼런스` |
| `/git` | Git 작업 | `/git commit "feat: 인증 추가"` |
| `/coordinator` | 멀티 에이전트 오케스트레이션 | `/coordinator 데이터베이스 스키마 마이그레이션` |
| `/explore` | 코드베이스 아키텍처 탐색 | `/explore 인증 모듈은 어떻게 작동하나요?` |
| `/security` | 보안 분석 | `/security 인증 모듈 취약점 스캔` |
| `/test` | 테스트 생성 및 실행 | `/test src/services/auth.ts --generate` |
| `/deploy` | 릴리스 준비 및 배포 | `/deploy release` |

---

## 에이전트

| 에이전트 | 책임 | 모델 |
|---------|------|------|
| **코디네이터** | 작업 분류, 워크플로우 조율, 에이전트 인계 관리 | Sonnet |
| **플래너** | 코드베이스 탐색, 구현 계획 + ops.json 설정 작성 | Sonnet |
| **리뷰어** | 다차원 계획 검증 -- 계획 품질(40%), 아키텍처(30%), 보안(30%) | Opus |
| **구현자** | 자동 백업과 함께 오퍼레이션 스크립트를 통해 승인된 계획 실행 | Sonnet |
| **검증자** | 품질 검증 -- 정적 분석(30%), 테스트(40%), 커버리지(30%) | Haiku |
| **디버거** | 4단계 체계적 디버깅을 사용한 읽기 전용 근본 원인 분석 | Opus |
| **문서화 담당** | 기술 문서 작성 및 유지 보수 | Haiku |
| **GitOps** | 브랜치, 커밋, PR 생성, 릴리스 관리 | Haiku |
| **탐색기** | 빠른 코드베이스 탐색, 패턴 발견, 아키텍처 매핑 | Sonnet |
| **테스터** | 전문 테스트 작성 -- 유닛, 통합, E2E, 커버리지 갭 분석 | Sonnet |
| **보안 스캐너** | OWASP Top 10 스캔, 시크릿 탐지, 의존성 CVE 분석 | Opus |
| **DevOps** | CI/CD 파이프라인, 컨테이너화, 배포, 코드형 인프라 | Sonnet |
| **데이터베이스 아키텍트** | 스키마 설계, 마이그레이션, 쿼리 최적화, 데이터 모델링 | Sonnet |

---

## 동작 모드

| 모드 | 설명 |
|------|------|
| **기본** | 완전한 설명과 출력 형식을 갖춘 일반 운영 |
| **브레인스토밍** | 구현 제약 없는 자유로운 아이디어 생성 |
| **토큰 효율** | 40-70% 토큰 절약을 목표로 하는 압축 출력 |

---

## 사양 기반 워크플로우

1. `specs/`에 사양을 작성
2. `/plan`을 실행하여 사양 기반 계획 수립
3. 리뷰어가 사양에 대해 검증
4. 검증자가 사양 준수를 확인

---

## 기여하기

기여를 환영합니다! 자세한 내용은 [기여 가이드](../CONTRIBUTING.md)를 참조하세요.

---

## 라이선스

MIT -- 자세한 내용은 [LICENSE](../LICENSE)를 참조하세요.
